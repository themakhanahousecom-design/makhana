"""Audio stays in memory. Vosk model loading happens only after user activation."""
import json
import multiprocessing
import queue
import re
import threading
import time
from pathlib import Path


class WakeGate:
    def __init__(self, seconds=12):
        self.seconds = seconds
        self.until = 0.0
        self.pattern = re.compile(r"(?:^|\s)(?:hey\s+)?(?:sidhu|सिद्धू|ਸਿੱਧੂ)(?:\s|[,!?.]|$)", re.I)

    def accept(self, text, now=None):
        now = time.monotonic() if now is None else now
        match = self.pattern.search(text)
        if match:
            self.until = now + self.seconds
            return text[match.end():].strip(), True
        if now < self.until:
            self.until = now + self.seconds
            return text.strip(), True
        return "", False


class VoiceService:
    def __init__(self, settings, on_command, on_status, on_partial, on_state=lambda state: None):
        self.settings = settings
        self.on_command, self.on_status, self.on_partial = on_command, on_status, on_partial
        self.on_state = on_state
        self.state = "muted"
        self.stop_event = threading.Event()
        self.thread = None
        self.speaking = threading.Event()

    def _status(self, state, message):
        if self.stop_event.is_set() and state != "muted":
            return
        self.state = state
        self.on_state(state)
        self.on_status(message)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self._status("loading", "Preparing local listener…")
        self.thread = threading.Thread(target=self._run, name="sidhu-listener", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()  # Stream is closed before mute is acknowledged.
        self._status("muted", "Microphone muted; audio capture stopped")

    def _run(self):
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
            if not Path(self.settings.model_path).is_dir() or not self.settings.model_path:
                raise RuntimeError("Select an extracted Vosk language model folder in Settings.")
            self._status("loading", "Loading local speech model…")
            model = Model(self.settings.model_path)
            gate = WakeGate(self.settings.followup_seconds)
            for attempt in range(3):
                if self.stop_event.is_set():
                    return
                audio = queue.Queue(maxsize=32)
                def callback(data, frames, timing, status):
                    if self.stop_event.is_set() or self.speaking.is_set():
                        return
                    try:
                        audio.put_nowait(bytes(data))
                    except queue.Full:
                        pass
                try:
                    recognizer = KaldiRecognizer(model, 16000)
                    with sd.RawInputStream(samplerate=16000, blocksize=4000, device=self.settings.microphone, dtype="int16", channels=1, callback=callback) as stream:
                        self._status("listening", "Listening locally — say Hey Sidhu")
                        while not self.stop_event.is_set():
                            if self.speaking.is_set():
                                recognizer.Reset()
                                while not audio.empty():
                                    try:
                                        audio.get_nowait()
                                    except queue.Empty:
                                        break
                                self.stop_event.wait(0.05)
                                continue
                            try:
                                chunk = audio.get(timeout=0.2)
                            except queue.Empty:
                                if not self.stop_event.is_set() and not getattr(stream, "active", True):
                                    raise RuntimeError("Audio input stream stopped unexpectedly.")
                                continue
                            if self.speaking.is_set():
                                recognizer.Reset()
                                continue
                            if recognizer.AcceptWaveform(chunk):
                                text = json.loads(recognizer.Result()).get("text", "")
                                # Recognition can finish after mute or speech output began.
                                if self.stop_event.is_set() or self.speaking.is_set():
                                    continue
                                command, accepted = gate.accept(text)
                                if accepted:
                                    if command:
                                        self.on_command(command)
                                    else:
                                        self._status("listening", "Wake phrase heard — ready for your command")
                            else:
                                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                                # Only surface transcription after activation, not ambient speech.
                                if not self.stop_event.is_set() and not self.speaking.is_set() and time.monotonic() < gate.until:
                                    self.on_partial(partial)
                    return
                except Exception:
                    if attempt == 2:
                        raise
                    self._status("recovering", "Audio device disconnected; retrying…")
                    if self.stop_event.wait(1 + attempt):
                        return
        except Exception as exc:
            self._status("error", f"Voice unavailable: {exc}")


def _speak_process(text, rate, voice_id, connection):
    """Isolated driver: cancellation can stop even a blocked SAPI backend."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.connect("started-word", lambda name, location, length: connection.send(("word", [location, length])))
        engine.say(text)
        engine.runAndWait()
        connection.send(("done", ""))
    except Exception as exc:
        connection.send(("error", str(exc)))
    finally:
        connection.close()


class Speaker:
    def __init__(self, settings, speaking, on_status, on_state=lambda state: None, context=None, target=None, on_word=lambda location, length: None):
        self.settings, self.speaking, self.on_status = settings, speaking, on_status
        self.on_state = on_state
        self.on_word = on_word
        self.context = context or multiprocessing.get_context("spawn")
        self.target = target or _speak_process
        self.messages = queue.Queue(maxsize=4)
        self.closed = threading.Event()
        self.lock = threading.RLock()
        self.generation = 0
        self.process = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="sidhu-speaker")
        self.thread.start()

    def say(self, text):
        with self.lock:
            if self.settings.speech_enabled and not self.closed.is_set():
                try:
                    self.messages.put_nowait((self.generation, text))
                except queue.Full:
                    self.on_status("Speech queue full; response remains visible in the dashboard.")

    def _stop_process(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
            self.process = None

    def stop(self):
        with self.lock:
            self.generation += 1
            while True:
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    break
            self._stop_process()
            self.speaking.clear()
            self.on_state("idle")
            self.on_status("Speech stopped; queued speech cleared.")

    def _run(self):
        while not self.closed.is_set():
            try:
                generation, text = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            receive = send = None
            try:
                receive, send = self.context.Pipe(duplex=False)
                with self.lock:
                    if generation != self.generation or self.closed.is_set() or not self.settings.speech_enabled:
                        continue
                    process = self.context.Process(target=self.target, args=(text, self.settings.speech_rate, self.settings.voice_id, send), daemon=True)
                    process.start()
                    # An unstarted process cannot be joined during cleanup.
                    self.process = process
                    send.close()
                    self.speaking.set()
                    self.on_state("speaking")
                    self.on_status("Speech output active (microphone commands suppressed).")
                deadline = time.monotonic() + 120
                while not self.closed.is_set():
                    with self.lock:
                        if generation != self.generation or self.closed.is_set():
                            break
                        process = self.process
                    if receive.poll(0.05):
                        try:
                            status, message = receive.recv()
                        except EOFError:
                            status, message = "error", "Speech worker exited without a result."
                        with self.lock:
                            if generation != self.generation or self.closed.is_set():
                                break
                            if status == "word":
                                self.on_word(*message)
                                continue
                            if status == "error":
                                self.on_status("Speech unavailable: " + message)
                            else:
                                self.on_status("Speech finished.")
                        break
                    if process is None or not process.is_alive():
                        with self.lock:
                            if generation == self.generation and not self.closed.is_set():
                                self.on_status("Speech worker exited without a result.")
                        break
                    if time.monotonic() >= deadline:
                        with self.lock:
                            if generation == self.generation and not self.closed.is_set():
                                self.on_status("Speech timed out after 120 seconds.")
                        break
            except Exception as exc:
                with self.lock:
                    if generation == self.generation and not self.closed.is_set():
                        self.on_status(f"Speech unavailable: {exc}")
            finally:
                if receive is not None:
                    receive.close()
                if send is not None:
                    send.close()
                with self.lock:
                    # Only this supervisor launches processes; stop() may have already reaped it.
                    self._stop_process()
                    self.speaking.clear()
                    self.on_state("idle")

    def close(self):
        self.closed.set()
        self.stop()
        if self.thread is not threading.current_thread():
            self.thread.join(timeout=3)
