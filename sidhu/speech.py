"""Installed voice discovery and native Windows speech events.

No recordings, cloned voices, downloaded models, or invented phoneme clocks are
used here. A SAPI voice may emit visemes; voices without them retain actual word
events. Driver access belongs in the isolated speech process, not the UI thread.
"""
from dataclasses import dataclass
import locale
import math
import multiprocessing
import sys


@dataclass(frozen=True)
class InstalledVoice:
    id: str
    name: str
    languages: tuple[str, ...] = ()
    gender: str = ""


def _language(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    # eSpeak prefixes language tags with a priority control byte.
    return str(value).lstrip("".join(chr(i) for i in range(32))).replace("_", "-").lower()


def voice_from_driver(voice):
    return InstalledVoice(str(voice.id), str(voice.name or voice.id),
                          tuple(_language(lang) for lang in (voice.languages or ())),
                          str(getattr(voice, "gender", "") or "").lower())


def preferred_voice(voices, requested=""):
    """Prefer an installed Punjabi/Indian male voice; otherwise keep OS default.

    Language/gender are provider metadata, not evidence of a particular accent,
    vocal depth, naturalness, identity, or a licensed artist's voice.
    """
    if requested:
        for voice in voices:
            if voice.id == requested:
                return voice
        raise ValueError("The selected speech voice is no longer installed. Choose an installed voice in Settings.")

    def rank(voice):
        langs = tuple(_language(lang) for lang in voice.languages)
        punjabi = any(lang == "pa" or lang.startswith("pa-") for lang in langs)
        indian = any(lang.endswith("-in") for lang in langs)
        male = voice.gender.lower() == "male"
        return 100 if punjabi and male else 80 if indian and male else 60 if punjabi else 0

    candidates = sorted(voices, key=rank, reverse=True)
    return candidates[0] if candidates and rank(candidates[0]) else None


def _sapi_voices(engine):
    voices = []
    tokens = engine.GetVoices()
    for index in range(tokens.Count):
        token = tokens.Item(index)
        def attribute(name):
            try:
                return token.GetAttribute(name)
            except Exception:
                return ""
        languages = []
        for language in attribute("Language").split(";"):
            try:
                languages.append(locale.windows_locale.get(int(language, 16), language).replace("_", "-").lower())
            except ValueError:
                pass
        voices.append(InstalledVoice(str(token.Id), str(token.GetDescription()), tuple(languages), attribute("Gender").lower()))
    return voices


def list_installed_voices():
    """Return installed driver metadata. Run off the UI thread (driver may block)."""
    if sys.platform == "win32":
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        try:
            engine = comtypes.client.CreateObject("SAPI.SpVoice")
            return _sapi_voices(engine)
        finally:
            engine = None
            comtypes.CoUninitialize()
    import pyttsx3
    engine = pyttsx3.init()
    try:
        return [voice_from_driver(voice) for voice in engine.getProperty("voices")]
    finally:
        engine.stop()


def _catalog_worker(connection):
    """Driver discovery is isolated because third-party COM drivers may block."""
    try:
        connection.send(("ok", list_installed_voices()[:256]))
    except Exception as exc:
        connection.send(("error", str(exc)))
    finally:
        connection.close()


def discover_installed_voices(timeout=6, *, target=None):
    """Bound driver discovery without holding the GUI/task pool indefinitely."""
    if not 0 < timeout <= 30:
        raise ValueError("Voice discovery timeout must be between 0 and 30 seconds.")
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=target or _catalog_worker, args=(send,), daemon=True)
    started = False
    try:
        process.start()
        started = True
        send.close()
        if not receive.poll(timeout):
            raise RuntimeError("Installed voice discovery timed out; the driver worker was stopped.")
        try:
            status, value = receive.recv()
        except EOFError as exc:
            raise RuntimeError("Installed voice driver exited without a result.") from exc
        if status != "ok":
            raise RuntimeError(str(value))
        if not isinstance(value, list) or len(value) > 256 or not all(isinstance(voice, InstalledVoice) for voice in value):
            raise RuntimeError("Installed voice driver returned an invalid catalog.")
        return value
    finally:
        receive.close()
        send.close()
        if started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            process.close()


def _utf16_boundary(text, offset):
    """SAPI character positions count UTF-16 code units, not Python code points."""
    encoded = text.encode("utf-16-le")
    return len(encoded[:max(0, int(offset)) * 2].decode("utf-16-le", errors="ignore"))


class SapiEventSink:
    def __init__(self, text, send):
        self.text, self.send = text, send
        self.finished = False
        self.has_visemes = False

    def _ISpeechVoiceEvents_StartStream(self, stream_number, stream_position):
        self.send(("sync", "word"))

    def _ISpeechVoiceEvents_Word(self, stream_number, stream_position, character, length):
        start = _utf16_boundary(self.text, character)
        end = _utf16_boundary(self.text, int(character) + int(length))
        if end > start:
            self.send(("word", [start, end - start]))

    def _ISpeechVoiceEvents_Viseme(self, stream_number, stream_position, duration, next_viseme, feature, current_viseme):
        if not self.has_visemes:
            self.send(("sync", "viseme"))
            self.has_visemes = True
        self.send(("viseme", [int(current_viseme), max(0, int(duration))]))

    def _ISpeechVoiceEvents_EndStream(self, stream_number, stream_position):
        self.finished = True


def speak_windows(text, rate, voice_id, send):
    """Play SAPI speech and relay audio-driver events as they are delivered.

    The process supervisor enforces the 120-second limit and kills this process
    on cancellation. A voice that omits visemes is honestly reported as word-only.
    """
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()
    engine = events = None
    try:
        engine = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = _sapi_voices(engine)
        chosen = preferred_voice(voices, voice_id)
        if chosen:
            tokens = engine.GetVoices()
            for index in range(tokens.Count):
                token = tokens.Item(index)
                if str(token.Id) == chosen.id:
                    engine.Voice = token
                    break
        # SAPI exposes a relative -10..10 rate, not a calibrated words/minute API.
        engine.Rate = max(-10, min(10, round(math.log(max(1, rate) / 165, 1.12))))
        # Start/end stream, word boundaries and visemes only; no audio capture.
        engine.EventInterests = 2 | 4 | 32 | 256
        sink = SapiEventSink(text, send)
        events = comtypes.client.GetEvents(engine, sink)
        # SVSFlagsAsync | SVSFIsNotXML: untrusted response text stays plain text.
        engine.Speak(text, 1 | 16)
        while not sink.finished:
            comtypes.client.PumpEvents(0.01)
    finally:
        try:
            if events is not None:
                events.disconnect()
        finally:
            engine = events = None
            comtypes.CoUninitialize()
