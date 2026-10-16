import multiprocessing
import os
import sys
import threading
import time
from types import SimpleNamespace
import pytest
from sidhu.config import Settings
from sidhu.voice import Speaker, VoiceService, pcm16_level


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


def viseme_event_speech(text, rate, voice, connection):
    connection.send(('sync', 'word'))
    connection.send(('word', [0, 5]))
    connection.send(('sync', 'viseme'))
    connection.send(('viseme', [15, 95]))
    connection.send(('viseme', [0, 40]))
    connection.send(('done', ''))
    connection.close()


def test_speech_activation_and_actual_viseme_events_are_forwarded():
    texts, words, visemes, syncs, statuses = [], [], [], [], []
    speaker = Speaker(Settings(), threading.Event(), statuses.append,
                      target=viseme_event_speech, on_text=texts.append,
                      on_word=lambda *event: words.append(event),
                      on_viseme=lambda *event: visemes.append(event), on_sync=syncs.append)
    try:
        speaker.say('hello')
        wait_for(lambda: 'Speech finished.' in statuses)
        assert texts == ['hello']
        assert words == [(0, 5)]
        assert visemes == [(15, 95), (0, 40)]
        assert syncs == ['word', 'viseme']
        assert any('actual Windows SAPI visemes' in status for status in statuses)
    finally:
        speaker.close()


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


@pytest.mark.parametrize('worker', [word_event_speech, viseme_event_speech])
def test_stop_discards_speech_event_already_received_by_supervisor(worker):
    context = multiprocessing.get_context('spawn')
    pending, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    statuses, words, visemes, syncs = [], [], [], []

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
                      target=worker, on_word=lambda *event: words.append(event),
                      on_viseme=lambda *event: visemes.append(event), on_sync=syncs.append)
    try:
        speaker.say('hello world')
        assert pending.wait(3)
        speaker.stop()
        stop_index = len(statuses)
        release.set()
        assert cleaned.wait(3)
        assert words == [] and visemes == [] and syncs == []
        assert not any('finished' in message or 'unavailable' in message for message in statuses[stop_index:])
    finally:
        release.set()
        speaker.close()


def test_pcm_level_uses_actual_samples_and_handles_partial_blocks():
    import struct
    assert pcm16_level(b'') == 0
    assert pcm16_level(b'\x00') == 0
    assert pcm16_level(struct.pack('<hhh', 0, 0, 0)) == 0
    assert pcm16_level(struct.pack('<hh', -16384, 16384)) == 0.5
    assert pcm16_level(struct.pack('<h', -32768) + b'\x01') == 1


def test_listener_emits_measured_level_without_ambient_transcripts(tmp_path, monkeypatch):
    import struct
    levels, partials, commands = [], [], []
    measured = threading.Event()

    class Stream:
        def __init__(self, callback, **kwargs):
            self.callback = callback

        def __enter__(self):
            self.callback(struct.pack('<hh', -16384, 16384), 2, None, None)
            return self

        def __exit__(self, *args):
            pass

    class Recognizer:
        def AcceptWaveform(self, data):
            return False

        def PartialResult(self):
            measured.set()
            return '{"partial": "private ambient speech"}'

    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=Stream))
    monkeypatch.setitem(sys.modules, 'vosk', SimpleNamespace(Model=lambda _: object(), KaldiRecognizer=lambda *args: Recognizer()))
    service = VoiceService(Settings(model_path=str(tmp_path)), commands.append,
                           lambda _: None, partials.append, on_level=levels.append)
    service.start()
    try:
        assert measured.wait(3)
    finally:
        service.stop()
    assert 0.5 in levels and levels[-1] == 0.0
    assert partials == commands == []


def test_stopped_speech_does_not_activate_queued_bubble():
    texts = []
    speaker = Speaker(Settings(), threading.Event(), lambda _: None,
                      target=hanging_speech, on_text=texts.append)
    try:
        speaker.say('active')
        wait_for(lambda: texts == ['active'])
        speaker.say('discarded')
        speaker.stop()
        time.sleep(0.15)
        assert texts == ['active']
    finally:
        speaker.close()


def test_non_windows_driver_reports_only_actual_word_callbacks(monkeypatch):
    import sidhu.voice as voice_module
    callbacks, properties, messages = {}, {}, []
    class Engine:
        def setProperty(self, name, value):
            properties[name] = value

        def getProperty(self, name):
            return [SimpleNamespace(id='pa-male', name='Installed voice', languages=['pa-IN'], gender='male')]

        def connect(self, name, callback):
            callbacks[name] = callback

        def say(self, text):
            assert text == 'hello'

        def runAndWait(self):
            callbacks['started-word']('hello', 0, 5)

    closed = []
    monkeypatch.setattr(voice_module, 'sys', SimpleNamespace(platform='linux'))
    monkeypatch.setitem(sys.modules, 'pyttsx3', SimpleNamespace(init=Engine))
    connection = SimpleNamespace(send=messages.append, close=lambda: closed.append(True))
    voice_module._speak_process('hello', 165, '', connection)
    assert messages == [('sync', 'word'), ('word', [0, 5]), ('done', '')]
    assert properties == {'rate': 165, 'voice': 'pa-male'}
    assert closed == [True]


def test_windows_driver_failure_never_replays_response_in_another_backend(monkeypatch):
    import sidhu.speech as speech_module
    import sidhu.voice as voice_module
    messages, closed = [], []
    def fail_after_start(*args):
        raise RuntimeError('audio driver failed')
    monkeypatch.setattr(voice_module, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(speech_module, 'speak_windows', fail_after_start)
    monkeypatch.setitem(sys.modules, 'pyttsx3', SimpleNamespace(init=lambda: pytest.fail('must not replay speech')))
    voice_module._speak_process('hello', 165, '', SimpleNamespace(send=messages.append, close=lambda: closed.append(True)))
    assert messages == [('error', 'audio driver failed')]
    assert closed == [True]


def test_utterance_tokens_distinguish_successive_speech_and_stop_invalidates_them():
    activated, events, statuses = [], [], []
    def capture(kind, *payload):
        events.append((speaker.utterance_id, kind, payload))
    speaker = Speaker(Settings(), threading.Event(), statuses.append, target=viseme_event_speech,
                      on_text=lambda text: activated.append((speaker.utterance_id, text)),
                      on_word=lambda *event: capture('word', *event),
                      on_viseme=lambda *event: capture('viseme', *event),
                      on_sync=lambda mode: capture('sync', mode))
    try:
        speaker.say('first')
        wait_for(lambda: statuses.count('Speech finished.') == 1)
        first = activated[0][0]
        assert all(token == first for token, _, _ in events)
        first_event_count = len(events)
        speaker.say('second')
        wait_for(lambda: statuses.count('Speech finished.') == 2)
        second = activated[1][0]
        assert second > first
        assert all(token == second for token, _, _ in events[first_event_count:])
        speaker.stop()
        assert speaker.utterance_id > second
    finally:
        speaker.close()


def test_callback_token_cannot_be_invalidated_mid_emission_by_stop():
    emitting, release, stopped = threading.Event(), threading.Event(), threading.Event()
    tokens = []
    def on_viseme(*event):
        tokens.append(speaker.utterance_id)
        emitting.set()
        assert release.wait(3)
        tokens.append(speaker.utterance_id)
    speaker = Speaker(Settings(), threading.Event(), lambda _: None,
                      target=viseme_event_speech, on_viseme=on_viseme)
    stopper = threading.Thread(target=lambda: (speaker.stop(), stopped.set()))
    try:
        speaker.say('hello')
        assert emitting.wait(3)
        stopper.start()
        assert not stopped.wait(0.05)
        release.set()
        assert stopped.wait(3)
        assert tokens[0] == tokens[1]
        assert speaker.utterance_id > tokens[0]
    finally:
        release.set()
        if stopper.ident is not None:
            stopper.join(timeout=3)
        speaker.close()
