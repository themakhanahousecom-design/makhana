"""Bounded, read-only tools restricted to explicitly approved local folders."""
import hashlib
import os
from pathlib import Path
import threading

TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.json', '.log', '.py', '.js', '.ts', '.html', '.css', '.yaml', '.yml', '.toml', '.xml', '.ini'}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_FILES = 20000
MAX_HASH_BYTES = 256 * 1024 * 1024


class FileTools:
    def __init__(self, settings, cancelled: threading.Event):
        self.settings, self.cancelled = settings, cancelled

    def roots(self):
        roots = []
        for value in self.settings.approved_folders:
            root = Path(value).expanduser().resolve()
            if root.is_dir() and root not in roots:
                roots.append(root)
        if not roots:
            raise RuntimeError('No existing approved folders. Configure them in Settings.')
        return roots

    def check_cancelled(self):
        if self.cancelled.is_set():
            raise RuntimeError('File operation cancelled. No files were changed.')

    def walk(self):
        seen = set()
        count = 0
        for root in self.roots():
            for directory, dirs, names in os.walk(root, followlinks=False):
                self.check_cancelled()
                # Empty directories also cost traversal work. Count entries
                # before filtering so ignored links cannot bypass the limit.
                count += len(dirs)
                if count > MAX_FILES:
                    raise RuntimeError(f'Search exceeded {MAX_FILES:,} entries. Choose a smaller approved folder.')
                dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink() and (Path(directory) / name).resolve().is_relative_to(root)]
                for name in names:
                    self.check_cancelled()
                    count += 1
                    if count > MAX_FILES:
                        raise RuntimeError(f'Search exceeded {MAX_FILES:,} entries. Choose a smaller approved folder.')
                    path = Path(directory) / name
                    try:
                        resolved = path.resolve()
                        if path.is_symlink() or not resolved.is_relative_to(root) or resolved in seen or not resolved.is_file():
                            continue
                        seen.add(resolved)
                        yield resolved
                    except OSError:
                        continue

    def resolve_file(self, value):
        self.check_cancelled()
        supplied = Path(value.strip().strip('"')).expanduser()
        if not str(supplied) or '..' in supplied.parts:
            raise ValueError('Use a file within approved folders without parent traversal.')
        roots = self.roots()
        candidates = [supplied] if supplied.is_absolute() else [root / supplied for root in roots]
        found = []
        for path in candidates:
            resolved = path.resolve()
            if not any(resolved.is_relative_to(root) for root in roots):
                continue
            # Reject explicit symlinks and symlink-containing paths, even within approved roots.
            if any(part.is_symlink() for part in [path, *path.parents]):
                continue
            if resolved.is_file() and resolved not in found:
                found.append(resolved)
        if len(found) != 1:
            raise ValueError('File is missing, ambiguous, a symlink, or outside approved folders. Specify its exact approved path.')
        return found[0]

    def _read(self, path):
        self.check_cancelled()
        if path.suffix.casefold() not in TEXT_EXTENSIONS:
            raise ValueError('Unsupported file type. Text previews support common plain-text formats only.')
        # Reject a final symlink at open time on platforms supporting O_NOFOLLOW.
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        with os.fdopen(descriptor, 'rb') as stream:
            raw = stream.read(MAX_TEXT_BYTES + 1)
        self.check_cancelled()
        if len(raw) > MAX_TEXT_BYTES:
            raise ValueError('File exceeds the 2 MiB text-preview limit.')
        if b'\x00' in raw:
            raise ValueError('Binary content cannot be previewed as text.')
        try:
            return raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('Text must use UTF-8 encoding.') from exc

    def read(self, value):
        path = self.resolve_file(value)
        text = self._read(path)
        return f'File: {path}\nUntrusted file content (preview capped at 12,000 characters):\n' + text[:12000]

    def recent(self):
        files = []
        for path in self.walk():
            try:
                files.append((path.stat().st_mtime, path))
            except OSError:
                continue
        files.sort(key=lambda item: item[0], reverse=True)
        return '\n'.join(str(path) for _, path in files[:20]) or 'No files in approved folders.'

    def find(self, query, *, pdf_only=False):
        """Search filenames using the same approved-root traversal as other tools."""
        query = query.strip().casefold()
        if not query or any(part in query for part in ('/', '\\', '..')):
            raise ValueError('Search by filename only, inside approved folders.')
        matches = []
        for path in self.walk():
            if (path.suffix.casefold() == '.pdf' if pdf_only else query in path.name.casefold()):
                try:
                    matches.append((path.stat().st_mtime, path))
                except OSError:
                    continue
        matches.sort(key=lambda item: item[0], reverse=True)
        return '\n'.join(str(path) for _, path in matches[:20]) or 'No matching files in approved folders.'

    def search_content(self, query):
        if not query.strip():
            raise ValueError('Supply nonempty text to search for.')
        matches, skipped, total = [], 0, 0
        for path in self.walk():
            if path.suffix.casefold() not in TEXT_EXTENSIONS:
                continue
            try:
                size = path.stat().st_size
                if total + size > 20 * 1024 * 1024:
                    return 'Content-search scan limit reached (20 MiB); results are partial.\n' + '\n'.join(matches)
                total += size
                text = self._read(path)
            except (OSError, ValueError):
                skipped += 1
                continue
            lines = text.splitlines()
            for number, line in enumerate(lines, 1):
                if query.casefold() in line.casefold():
                    matches.append(f'{path}:{number}: {line[:240]}')
                    break
            if len(matches) >= 20:
                return 'First 20 matching files (scan stopped).\n' + '\n'.join(matches)
        return f'Skipped unreadable/unsupported-encoding/oversized text files: {skipped}.\n' + ('\n'.join(matches) or 'No matching text in scanned supported files.')

    def duplicates(self):
        sizes = {}
        skipped = 0
        for path in self.walk():
            try:
                sizes.setdefault(path.stat().st_size, []).append(path)
            except OSError:
                skipped += 1
        hashes, consumed = {}, 0
        for size, paths in sizes.items():
            if len(paths) < 2:
                continue
            for path in paths:
                self.check_cancelled()
                if consumed + size > MAX_HASH_BYTES:
                    raise RuntimeError('Duplicate scan exceeded the 256 MiB read budget; choose a smaller folder. No files were changed.')
                try:
                    digest = hashlib.sha256()
                    read_bytes = 0
                    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
                    with os.fdopen(descriptor, 'rb') as stream:
                        before = os.fstat(stream.fileno())
                        while chunk := stream.read(65536):
                            consumed += len(chunk)
                            read_bytes += len(chunk)
                            self.check_cancelled()
                            if consumed > MAX_HASH_BYTES:
                                raise RuntimeError('Duplicate scan exceeded its read budget. No files were changed.')
                            digest.update(chunk)
                        after = os.fstat(stream.fileno())
                    if read_bytes != size or before.st_mtime_ns != after.st_mtime_ns or before.st_size != after.st_size:
                        skipped += 1
                        continue
                    hashes.setdefault((size, digest.hexdigest()), []).append(path)
                except OSError:
                    skipped += 1
        groups = [paths for paths in hashes.values() if len(paths) > 1]
        report = '\n\n'.join('\n'.join(str(path) for path in group) for group in groups[:30])
        return f'SHA-256 duplicate groups: {len(groups)}; skipped changed/unreadable files: {skipped}. No files were changed.\n' + (report or 'No byte-identical duplicates found.')
