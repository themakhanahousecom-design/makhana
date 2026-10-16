from pathlib import Path
import threading
import httpx
import pytest
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
from sidhu.voice import WakeGate


class Tools:
    def __init__(self):
        self.calls = []
    def launch(self, name):
        self.calls.append(name)
        return 'dispatch accepted'
    def website(self, url):
        self.calls.append(url)
        return 'dispatch accepted; load unverified'
    def volume(self, value):
        self.calls.append(value)
        return f'volume {value}'


@pytest.fixture
def core(tmp_path):
    settings = Settings(approved_folders=[str(tmp_path / 'allowed')])
    (tmp_path / 'allowed').mkdir()
    return Engine(settings, Memory(tmp_path / 'memory.db'), Tools())


@pytest.mark.parametrize('command', ['open chrome', 'Chrome kholo', 'क्रोम खोलो', 'ਕ੍ਰੋਮ ਖੋਲ'])
def test_multilingual_launch(core, command):
    assert core.execute(command).ok
    assert core.tools.calls == ['chrome']


def test_permission_enforced(core):
    core.settings.allowed_apps = []
    assert not core.execute('open chrome').ok
    assert not core.tools.calls


@pytest.mark.parametrize('command', ['pay someone', 'submit otp', 'delete file', 'extract password', 'पैसे भेजो', 'disable security'])
def test_sensitive_actions_blocked(core, command):
    assert not core.execute(command).ok
    assert not core.tools.calls


def test_unknown_shell_not_executed(core):
    assert not core.execute('powershell Remove-Item C:/Users -Recurse').ok
    assert not core.tools.calls


def test_memory_disabled_does_not_write(core):
    assert not core.execute('remember hello').ok
    assert not core.memory.path.exists()


def test_memory_persistence_and_delete(core):
    core.settings.memory_enabled = True
    assert core.execute("remember Sidhu's note").ok
    reopened = Memory(core.memory.path)
    assert reopened.list() == [(1, "Sidhu's note")]
    reopened.clear()
    assert reopened.list() == []


def test_search_cannot_escape_approved_folder(core, tmp_path):
    allowed = tmp_path / 'allowed'
    (allowed / 'report.pdf').write_text('inside')
    (tmp_path / 'secret.pdf').write_text('outside')
    result = core.execute('latest pdf')
    assert result.ok
    assert 'report.pdf' in result.message
    assert 'secret.pdf' not in result.message
    assert 'leak.pdf' not in result.message
    assert not core.execute('find ../secret').ok


def test_volume_bounds(core):
    assert not core.execute('volume 101').ok
    assert core.execute('volume 50').ok
    assert core.tools.calls == [50]


def test_url_rejects_credentials(core):
    assert not core.execute('open https://user:pass@example.com').ok
    assert not core.execute('open http://example.com').ok
    assert core.execute('open https://example.com').ok
    assert core.tools.calls == ['https://example.com']


def test_actual_diagnostics(core):
    result = core.execute('diagnostics')
    assert result.ok and 'GiB' in result.message and 'CPU' in result.message


def test_tool_error_is_not_success(core):
    def fail(name):
        raise RuntimeError('application missing')
    core.tools.launch = fail
    result = core.execute('open chrome')
    assert not result.ok and 'application missing' in result.message


def test_ai_unconfigured(core):
    assert not core.execute('ask hello').ok


def test_ai_http_cloud_rejected(core):
    core.settings.ai_model = 'test'
    core.settings.ai_base_url = 'http://example.com/v1'
    assert not core.execute('ask hello').ok


def test_ai_real_http_transport_contract(core, monkeypatch):
    core.settings.ai_model = 'test'
    def handler(request):
        assert request.url.path == '/v1/chat/completions'
        assert b'cannot execute tools' in request.content
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Hello'}}]})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    assert core.execute('ask hi').message == 'Hello'
    assert core.tools.calls == []


def test_ai_network_failure_reported(core, monkeypatch):
    core.settings.ai_model = 'test'
    def handler(request):
        raise httpx.ConnectError('offline', request=request)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    result = core.execute('ask hi')
    assert not result.ok and 'request failed' in result.message


def test_wake_gate_followup_and_expiry():
    gate = WakeGate(seconds=10)
    assert gate.accept('open chrome', 1) == ('', False)
    assert gate.accept('hey sidhu open chrome', 2) == ('open chrome', True)
    assert gate.accept('battery', 3) == ('battery', True)
    assert gate.accept('battery', 20) == ('', False)
    assert gate.accept('sidhu', 21) == ('', True)
    assert gate.accept('sidhuism open chrome', 40) == ('', False)


def test_settings_roundtrip(tmp_path):
    path = tmp_path / 'config.json'
    settings = Settings(memory_enabled=True, microphone=3)
    settings.save(path)
    loaded = Settings.load(path)
    assert loaded == settings
    assert not path.with_suffix('.tmp').exists()


def test_cancel_command_sets_event(core):
    result = core.execute('cancel')
    assert result.ok and core.cancelled.is_set()


def test_file_search_cancel_during_traversal(core, monkeypatch, tmp_path):
    import sidhu.core as module
    def walk(*args, **kwargs):
        core.cancelled.set()
        yield str(tmp_path / 'allowed'), [], ['a.pdf']
    monkeypatch.setattr(module.os, 'walk', walk)
    result = core.execute('latest pdf')
    assert not result.ok and 'cancelled' in result.message


def test_missing_model_reports_unavailable(tmp_path):
    from sidhu.voice import VoiceService
    states = []
    voice = VoiceService(Settings(model_path=str(tmp_path / 'missing')), lambda _: pytest.fail('unexpected command'), states.append, lambda _: None)
    voice.start()
    voice.thread.join(timeout=10)
    assert not voice.thread.is_alive()
    assert any('unavailable' in state for state in states)


@pytest.mark.parametrize('command', ["don't open chrome", 'do not open chrome', 'क्रोम मत खोलो'])
def test_negation_does_not_launch(core, command):
    assert not core.execute(command).ok
    assert not core.tools.calls


def test_data_directory_override(monkeypatch, tmp_path):
    from sidhu.config import data_dir
    monkeypatch.setenv('SIDHU_DATA_DIR', str(tmp_path / 'sidhu-data'))
    assert data_dir() == tmp_path / 'sidhu-data'
    assert data_dir().is_dir()


def test_search_rejects_symlinks(core, tmp_path):
    allowed = tmp_path / 'allowed'
    (tmp_path / 'secret.pdf').write_text('outside')
    try:
        (allowed / 'leak.pdf').symlink_to(tmp_path / 'secret.pdf')
        (allowed / 'directory').symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip('This Windows session does not permit creating test symlinks')
    result = core.execute('latest pdf')
    assert result.ok
    assert 'leak.pdf' not in result.message
    assert 'secret.pdf' not in result.message
