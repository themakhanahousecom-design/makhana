import multiprocessing
import os
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from sidhu.config import Settings
from sidhu.voice import Speaker, VoiceService


def wait_for(predicate, timeout=5):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), 'Timed out waiting for voice lifecycle transition'


def hanging_speech(text, rate, voice, connection):
    time.sleep(60)


def successful_speech(text, rate, voice, connection):
    connection.send(('done', ''))
    connection.close()


def failing_speech(text, rate, voice, connection):
    connection.send(('error', 'No audio output device'))
    connection.close()


def crashed_speech(text, rate, voice, connection):
    os._exit(23)


def test_stop_terminates_blocked_speech_and_clears_queue():
    speaking = threading.Event()
    speaker = Speaker(Settings(), speaking, lambda _: None, target=hanging_speech)
    try:
        speaker.say('long response')
        wait_for(speaking.is_set)
        process = speaker.process
        speaker.say('queued response')
        speaker.stop()
        assert not process.is_alive()
        assert not speaking.is_set()
        assert speaker.messages.empty()
        # Subsequent output must still work after the interrupted worker.
        speaker.target = successful_speech
        speaker.say('new response')
        wait_for(speaking.is_set)
        wait_for(lambda: not speaking.is_set())
    finally:
        speaker.close()
    assert not speaker.thread.is_alive()


def test_speech_failure_is_reported_and_state_resets():
    statuses, states = [], []
    speaking = threading.Event()
    speaker = Speaker(Settings(), speaking, statuses.append, states.append, target=failing_speech)
    try:
        speaker.say('hello')
        wait_for(lambda: any('No audio output device' in text for text in statuses))
        wait_for(lambda: not speaking.is_set())
        assert 'speaking' in states and states[-1] == 'idle'
    finally:
        speaker.close()


def test_disabled_speech_does_not_start_worker():
    speaker = Speaker(Settings(speech_enabled=False), threading.Event(), lambda _: None)
    try:
        speaker.say('no audio')
        assert speaker.messages.empty() and speaker.process is None
    finally:
        speaker.close()


def test_mute_closes_capture_before_acknowledging(tmp_path, monkeypatch):
    active, closed = threading.Event(), threading.Event()
    states = []
    class Stream:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            active.set()
        def __exit__(self, *args):
            closed.set()
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=lambda *args: object()))
    service = VoiceService(Settings(model_path=str(tmp_path)), lambda _: None, lambda _: None, lambda _: None, states.append)
    service.start()
    try:
        assert active.wait(3)
    finally:
        service.stop()
    assert closed.is_set()
    assert not service.thread.is_alive()
    assert service.state == 'muted' and states[-1] == 'muted'


def test_audio_failure_exhausts_bounded_retries(tmp_path, monkeypatch):
    attempts, states = [], []
    def fail(**kwargs):
        attempts.append(1)
        raise RuntimeError('device unavailable')
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=fail))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=lambda *args: object()))
    service = VoiceService(Settings(model_path=str(tmp_path)), lambda _: None, lambda _: None, lambda _: None, states.append)
    service.start()
    service.thread.join(timeout=6)
    assert not service.thread.is_alive()
    assert len(attempts) == 3
    assert states == ['loading', 'loading', 'recovering', 'recovering', 'error']


def test_stopped_input_stream_exhausts_bounded_retries(tmp_path, monkeypatch):
    attempts, closed, statuses = [], [], []

    class Stream:
        active = False

        def __init__(self, **kwargs):
            attempts.append(1)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(1)

    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=lambda *args: object()))
    service = VoiceService(Settings(model_path=str(tmp_path)), lambda _: None, statuses.append, lambda _: None)
    service.start()
    try:
        service.thread.join(timeout=6)
        assert not service.thread.is_alive()
        assert len(attempts) == len(closed) == 3
        assert service.state == 'error'
        assert 'Audio input stream stopped unexpectedly.' in statuses[-1]
    finally:
        service.stop()


def test_recognized_wake_to_command_to_result(tmp_path, monkeypatch):
    """Exercise listener → gate → real router; acoustic recognizer/device are test doubles."""
    import json
    from sidhu.core import Engine
    from sidhu.memory import Memory
    results, calls = [], []
    completed = threading.Event()
    class Stream:
        def __init__(self, callback, **kwargs):
            self.callback = callback
        def __enter__(self):
            self.callback(b'first transcript', 4000, None, None)
            self.callback(b'second transcript', 4000, None, None)
        def __exit__(self, *args):
            pass
    class Recognizer:
        def __init__(self, *args):
            self.utterances = iter(['open chrome', 'hey sidhu open notepad'])
        def AcceptWaveform(self, chunk):
            return True
        def Result(self):
            return json.dumps({'text': next(self.utterances)})
    class Tools:
        def launch(self, name):
            calls.append(name)
            return 'Verified test-double dispatch'
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=Recognizer))
    settings = Settings(model_path=str(tmp_path))
    engine = Engine(settings, Memory(tmp_path / 'notes.db'), Tools())
    def execute(command):
        results.append(engine.execute(command))
        completed.set()
    service = VoiceService(settings, execute, lambda _: None, lambda _: None)
    service.start()
    try:
        assert completed.wait(3)
    finally:
        service.stop()
    assert calls == ['notepad']  # Ambient command without wake phrase must not dispatch.
    assert len(results) == 1 and results[0].ok


def word_event_speech(text, rate, voice, connection):
    connection.send(('word', [0, 5]))
    connection.send(('word', [6, 5]))
    connection.send(('done', ''))
    connection.close()


def test_actual_worker_word_events_forwarded_without_invented_timing():
    words, statuses = [], []
    speaking = threading.Event()
    speaker = Speaker(Settings(), speaking, statuses.append, target=word_event_speech, on_word=lambda offset, length: words.append((offset, length)))
    try:
        speaker.say('hello world')
        wait_for(lambda: 'Speech finished.' in statuses)
        assert words == [(0, 5), (6, 5)]
        wait_for(lambda: not speaking.is_set())
    finally:
        speaker.close()


@pytest.mark.parametrize('partial', [False, True])
def test_mute_discards_recognition_finishing_after_stop(tmp_path, monkeypatch, partial):
    pending, release = threading.Event(), threading.Event()
    commands, partials, states = [], [], []

    class Stream:
        def __init__(self, callback, **kwargs):
            self.callback = callback

        def __enter__(self):
            self.callback(b'wake', 4000, None, None)
            if partial:
                self.callback(b'pending', 4000, None, None)

        def __exit__(self, *args):
            pass

    class Recognizer:
        def __init__(self, *args):
            self.first = True

        def AcceptWaveform(self, chunk):
            return not partial or chunk == b'wake'

        def Result(self):
            if partial and self.first:
                self.first = False
                return '{"text": "hey sidhu"}'
            pending.set()
            assert release.wait(3)
            return '{"text": "hey sidhu open notepad"}'

        def PartialResult(self):
            pending.set()
            assert release.wait(3)
            return '{"partial": "open notepad"}'

    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=Recognizer))
    service = VoiceService(Settings(model_path=str(tmp_path)), commands.append, lambda _: None, partials.append, states.append)
    service.start()
    muting = threading.Thread(target=service.stop)
    try:
        assert pending.wait(3)
        muting.start()
        wait_for(service.stop_event.is_set)
    finally:
        release.set()
        if muting.ident is not None:
            muting.join(timeout=3)
        service.stop()
    assert commands == [] and partials == []
    assert service.state == 'muted' and states[-1] == 'muted'
    assert not service.thread.is_alive()


@pytest.mark.parametrize('failure', ['pipe', 'start'])
def test_speech_supervisor_recovers_from_worker_startup_failure(failure):
    context = multiprocessing.get_context('spawn')
    statuses, attempts = [], []

    def create_pipe(**kwargs):
        if failure == 'pipe' and not attempts:
            attempts.append(1)
            raise RuntimeError('test pipe creation failure')
        return context.Pipe(**kwargs)

    def create_process(**kwargs):
        if failure == 'start' and not attempts:
            attempts.append(1)
            def fail_start():
                raise RuntimeError('test worker startup failure')
            return SimpleNamespace(start=fail_start)
        return context.Process(**kwargs)

    speaker = Speaker(Settings(), threading.Event(), statuses.append,
                      context=SimpleNamespace(Pipe=create_pipe, Process=create_process), target=successful_speech)
    try:
        speaker.say('first response')
        wait_for(lambda: any('failure' in message for message in statuses))
        assert speaker.thread.is_alive()
        speaker.say('second response')
        wait_for(lambda: 'Speech finished.' in statuses)
    finally:
        speaker.close()
    assert not speaker.thread.is_alive()


def test_crashed_speech_worker_reports_failure_and_cleans_up():
    statuses = []
    speaking = threading.Event()
    speaker = Speaker(Settings(), speaking, statuses.append, target=crashed_speech)
    try:
        speaker.say('response')
        wait_for(lambda: any('without a result' in message for message in statuses))
        wait_for(lambda: speaker.process is None and not speaking.is_set())
        assert speaker.thread.is_alive()
    finally:
        speaker.close()


def test_stop_discards_speech_event_already_received_by_supervisor():
    context = multiprocessing.get_context('spawn')
    pending, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    statuses, words = [], []

    class PendingReceive:
        def __init__(self, receive):
            self.receive = receive

        def poll(self, timeout):
            return self.receive.poll(timeout)

        def recv(self):
            message = self.receive.recv()
            pending.set()
            assert release.wait(3)
            return message

        def close(self):
            self.receive.close()
            cleaned.set()

    def create_pipe(**kwargs):
        receive, send = context.Pipe(**kwargs)
        return PendingReceive(receive), send

    speaker = Speaker(Settings(), threading.Event(), statuses.append,
                      context=SimpleNamespace(Pipe=create_pipe, Process=context.Process),
                      target=word_event_speech, on_word=lambda *event: words.append(event))
    try:
        speaker.say('hello world')
        assert pending.wait(3)
        speaker.stop()
        stop_index = len(statuses)
        release.set()
        assert cleaned.wait(3)
        assert words == []
        assert not any('finished' in message or 'unavailable' in message for message in statuses[stop_index:])
    finally:
        release.set()
        speaker.close()
