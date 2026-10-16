"""SAPI protocol tests use COM doubles; no Windows audio output is claimed."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from sidhu.speech import InstalledVoice, SapiEventSink, preferred_voice, voice_from_driver


def catalog_success(connection):
    connection.send(("ok", [InstalledVoice("pa-test", "Test driver voice", ("pa-in",), "male")]))
    connection.close()


def catalog_error(connection):
    connection.send(("error", "Driver unavailable"))
    connection.close()


def catalog_blocked(connection):
    import time
    time.sleep(60)


def test_voice_discovery_process_returns_metadata_and_driver_failure():
    from sidhu.speech import discover_installed_voices
    assert discover_installed_voices(target=catalog_success)[0].id == "pa-test"
    with pytest.raises(RuntimeError, match="Driver unavailable"):
        discover_installed_voices(target=catalog_error)


def test_voice_discovery_timeout_reaps_a_blocked_driver():
    import multiprocessing
    from sidhu.speech import discover_installed_voices
    before = {process.pid for process in multiprocessing.active_children()}
    with pytest.raises(RuntimeError, match="timed out"):
        discover_installed_voices(timeout=.05, target=catalog_blocked)
    assert {process.pid for process in multiprocessing.active_children()} == before


def test_voice_selection_prefers_installed_metadata_and_respects_explicit_id():
    default = InstalledVoice('en', 'System voice', ('en-US',), 'male')
    indian = InstalledVoice('hi', 'Installed Hindi voice', ('hi-IN',), 'male')
    punjabi = InstalledVoice('pa', 'Installed Punjabi voice', ('pa-IN',), 'male')
    assert preferred_voice([default]) is None  # Preserve OS default without suitable metadata.
    assert preferred_voice([default, indian]) == indian
    assert preferred_voice([default, indian, punjabi]) == punjabi
    assert preferred_voice([default, indian, punjabi], 'en') == default
    with pytest.raises(ValueError, match='no longer installed'):
        preferred_voice([default], 'removed')


def test_voice_metadata_normalizes_espeak_language_priority():
    voice = voice_from_driver(SimpleNamespace(id='pa', name='Punjabi', languages=[b'\x05pa_IN'], gender='Male'))
    assert voice.languages == ('pa-in',)
    assert preferred_voice([voice]) == voice


def test_sapi_word_boundaries_map_utf16_and_visemes_have_driver_durations():
    messages = []
    sink = SapiEventSink('😀 hello', messages.append)
    sink._ISpeechVoiceEvents_StartStream(1, 0)
    sink._ISpeechVoiceEvents_Word(1, 0, 3, 5)
    sink._ISpeechVoiceEvents_Viseme(1, 0, 93, 5, 0, 15)
    sink._ISpeechVoiceEvents_Viseme(1, 0, 32, 0, 0, 5)
    sink._ISpeechVoiceEvents_EndStream(1, 0)
    assert messages == [('sync', 'word'), ('word', [2, 5]), ('sync', 'viseme'),
                        ('viseme', [15, 93]), ('viseme', [5, 32])]
    assert sink.finished


def test_sapi_word_only_voice_does_not_claim_visemes():
    messages = []
    sink = SapiEventSink('hello', messages.append)
    sink._ISpeechVoiceEvents_StartStream(1, 0)
    sink._ISpeechVoiceEvents_Word(1, 0, 0, 5)
    sink._ISpeechVoiceEvents_EndStream(1, 0)
    assert messages == [('sync', 'word'), ('word', [0, 5])]
    assert not sink.has_visemes


def fake_com(monkeypatch, engine, emit):
    import sidhu.speech as speech
    events, sink_store = [], []
    com = ModuleType('comtypes')
    com.__path__ = []
    com.CoInitialize = lambda: events.append('initialize')
    com.CoUninitialize = lambda: events.append('uninitialize')
    client = ModuleType('comtypes.client')
    client.CreateObject = lambda progid: engine
    def get_events(target, sink):
        assert target is engine
        sink_store.append(sink)
        return SimpleNamespace(disconnect=lambda: events.append('disconnect'))
    client.GetEvents = get_events
    client.PumpEvents = lambda duration: emit(sink_store[0])
    com.client = client
    monkeypatch.setitem(sys.modules, 'comtypes', com)
    monkeypatch.setitem(sys.modules, 'comtypes.client', client)
    monkeypatch.setattr(speech, 'sys', SimpleNamespace(platform='win32'))
    return events


def sapi_engine():
    token = SimpleNamespace(Id='installed-pa', GetDescription=lambda: 'Punjabi male',
                            GetAttribute=lambda name: {'Language': '446', 'Gender': 'Male'}[name])
    calls = []
    engine = SimpleNamespace(GetVoices=lambda: SimpleNamespace(Count=1, Item=lambda _: token),
                             Speak=lambda text, flags: calls.append((text, flags)))
    return engine, calls


def test_native_sapi_speaks_plain_text_and_pumps_actual_events(monkeypatch):
    from sidhu.speech import speak_windows
    messages = []
    engine, calls = sapi_engine()

    def emit(sink):
        sink._ISpeechVoiceEvents_StartStream(1, 0)
        sink._ISpeechVoiceEvents_Viseme(1, 0, 80, 0, 0, 1)
        sink._ISpeechVoiceEvents_EndStream(1, 0)

    lifecycle = fake_com(monkeypatch, engine, emit)
    speak_windows('<pitch>plain response</pitch>', 165, '', messages.append)
    assert calls == [('<pitch>plain response</pitch>', 17)]
    assert engine.Voice.Id == 'installed-pa'
    assert engine.Rate == 0 and engine.EventInterests == 294
    assert messages == [('sync', 'word'), ('sync', 'viseme'), ('viseme', [1, 80])]
    assert lifecycle == ['initialize', 'disconnect', 'uninitialize']


def test_native_inventory_reports_installed_languages_without_voice_claims(monkeypatch):
    from sidhu.speech import list_installed_voices
    engine, _ = sapi_engine()
    lifecycle = fake_com(monkeypatch, engine, lambda sink: None)
    voices = list_installed_voices()
    assert voices == [InstalledVoice('installed-pa', 'Punjabi male', ('pa-in',), 'male')]
    assert lifecycle == ['initialize', 'uninitialize']


def test_native_sapi_releases_com_after_driver_failure(monkeypatch):
    from sidhu.speech import speak_windows
    engine, _ = sapi_engine()
    def fail(text, flags):
        raise RuntimeError('audio device unavailable')
    engine.Speak = fail
    lifecycle = fake_com(monkeypatch, engine, lambda sink: None)
    with pytest.raises(RuntimeError, match='audio device unavailable'):
        speak_windows('hello', 165, '', lambda message: None)
    assert lifecycle == ['initialize', 'disconnect', 'uninitialize']
