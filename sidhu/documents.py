"""Local, read-only document previews and deterministic extractive summaries.

PDF extraction runs in a disposable child process so cancellation and a wall
timeout can stop malformed input. POSIX workers additionally cap address space;
Windows still relies on the timeout rather than an operating-system memory cap.
"""
from collections import Counter
import io
import json
import math
import multiprocessing
import os
import re
import threading
import time

from .files import FileTools


MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_EXTRACTED_CHARACTERS = 120000
MAX_PREVIEW_CHARACTERS = 12000
MAX_SUMMARY_CHARACTERS = 2400
PDF_TIMEOUT_SECONDS = 12
PDF_MEMORY_BYTES = 512 * 1024 * 1024
MAX_WORKER_RESPONSE_BYTES = 1024 * 1024


def _pdf_worker(data, page_limit, character_limit, connection):
    """Only this child imports and runs the optional PDF parser."""
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (PDF_MEMORY_BYTES, PDF_MEMORY_BYTES))
        except (ImportError, OSError, ValueError):
            pass  # Windows has no resource module; the parent enforces time.
        import logging
        logging.disable(logging.CRITICAL)
        try:
            from pypdf import PdfReader
        except ImportError:
            response = {"error": 'PDF support requires the optional documents dependency: pip install ".[documents]".'}
        else:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                response = {"error": "Encrypted PDFs are unsupported. Choose an unencrypted local copy; no password was requested."}
            else:
                count = len(reader.pages)
                pages, consumed, read_count, truncated = [], 0, 0, count > page_limit
                for index in range(min(count, page_limit)):
                    text = reader.pages[index].extract_text() or ""
                    remaining = character_limit - consumed
                    pages.append(text[:remaining])
                    consumed += min(len(text), remaining)
                    read_count += 1
                    if len(text) > remaining or (consumed >= character_limit and index + 1 < count):
                        truncated = True
                        break
                response = {"text": "\n".join(pages)[:character_limit], "pages": count,
                            "read_pages": read_count, "truncated": truncated}
    except MemoryError:
        response = {"error": "PDF extraction exceeded the parser memory limit. Choose a smaller PDF."}
    except Exception as exc:
        response = {"error": f"Unreadable or unsupported PDF ({type(exc).__name__}). No document content was sent to an AI provider."}
    try:
        connection.send_bytes(json.dumps(response, ensure_ascii=True).encode("utf-8"))
    finally:
        connection.close()


class DocumentTools:
    def __init__(self, settings, cancelled: threading.Event):
        self.files = FileTools(settings, cancelled)
        self.cancelled = cancelled

    def _extract_pdf(self, data):
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_pdf_worker,
                                  args=(data, MAX_PDF_PAGES, MAX_EXTRACTED_CHARACTERS, sender),
                                  daemon=True)
        deadline = time.monotonic() + PDF_TIMEOUT_SECONDS
        try:
            process.start()
            sender.close()
            while True:
                self.files.check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"PDF extraction exceeded {PDF_TIMEOUT_SECONDS:g} seconds and was stopped. Choose a smaller PDF.")
                if receiver.poll(min(0.05, remaining)):
                    try:
                        response = json.loads(receiver.recv_bytes(MAX_WORKER_RESPONSE_BYTES))
                    except (EOFError, OSError, ValueError) as exc:
                        raise ValueError("PDF parser stopped without readable output. The file may be malformed or exceed parser limits.") from exc
                    if "error" in response:
                        raise ValueError(response["error"])
                    return response
                if not process.is_alive():
                    raise ValueError("PDF parser stopped unexpectedly. The file may be malformed or exceed parser limits.")
        finally:
            sender.close()
            receiver.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=2)
                if not process.is_alive():
                    process.close()
            else:
                process.close()

    def _load(self, value):
        path = self.files.resolve_file(value)
        if path.suffix.casefold() != ".pdf":
            text = self.files._read(path)
            partial = len(text) > MAX_EXTRACTED_CHARACTERS
            detail = f"Text document; extraction capped at {MAX_EXTRACTED_CHARACTERS:,} characters."
            text = text[:MAX_EXTRACTED_CHARACTERS]
        else:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
            with os.fdopen(descriptor, "rb") as stream:
                if os.fstat(stream.fileno()).st_size > MAX_PDF_BYTES:
                    raise ValueError("PDF exceeds the 10 MiB input limit.")
                data = stream.read(MAX_PDF_BYTES + 1)
            self.files.check_cancelled()
            if len(data) > MAX_PDF_BYTES:
                raise ValueError("PDF exceeds the 10 MiB input limit.")
            result = self._extract_pdf(data)
            text, partial = result["text"], result["truncated"]
            detail = f'PDF text extracted from {result["read_pages"]} of {result["pages"]} pages (maximum {MAX_PDF_PAGES} pages, {MAX_EXTRACTED_CHARACTERS:,} characters).'
            if not text.strip():
                raise ValueError("No extractable text in the inspected PDF pages. Scanned/image-only PDFs require OCR, which is not implemented.")
        self.files.check_cancelled()
        if not text.strip():
            raise ValueError("The document contains no readable text.")
        if partial:
            detail += " Partial document: limits excluded some content."
        return path, text, detail

    def preview(self, value):
        path, text, detail = self._load(value)
        return (f"Document: {path}\n{detail}\n"
                f"Untrusted document content (preview capped at {MAX_PREVIEW_CHARACTERS:,} characters):\n"
                + text[:MAX_PREVIEW_CHARACTERS])

    def summarize(self, value):
        path, text, detail = self._load(value)
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?।])\s+|\n+", text) if sentence.strip()]
        stopwords = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were", "with"}
        tokens = [[word for word in re.findall(r"\w+", sentence.casefold()) if word not in stopwords] for sentence in sentences]
        frequency = Counter(word for words in tokens for word in words)
        scores = [(sum(frequency[word] for word in words) / math.sqrt(max(1, len(words))), index)
                  for index, words in enumerate(tokens)]
        chosen = sorted(index for _, index in sorted(scores, key=lambda item: (-item[0], item[1]))[:5])
        excerpts, used = [], 0
        for index in chosen:
            self.files.check_cancelled()
            remaining = MAX_SUMMARY_CHARACTERS - used
            if remaining <= 0:
                break
            sentence = sentences[index]
            excerpt = sentence[:remaining]
            excerpts.append(excerpt + (" [excerpt truncated]" if len(sentence) > remaining else ""))
            used += len(excerpt)
        return (f"Document: {path}\n{detail}\n"
                "Local extractive summary: copied excerpts selected by word frequency; no AI provider used.\n"
                "Untrusted document content; excerpts are capped at 2,400 characters:\n"
                + "\n".join(f"- {excerpt}" for excerpt in excerpts))
