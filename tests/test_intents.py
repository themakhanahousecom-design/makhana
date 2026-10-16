import pytest
from sidhu.core import Engine
from sidhu.config import Settings
from sidhu.memory import Memory
from sidhu.intents import app_intent


class Tools:
    def __init__(self):
        self.calls = []
    def launch(self, name):
        self.calls.append(name)
        return 'dispatch accepted'
    def website(self, url):
        self.calls.append(url)
        return 'website dispatch accepted'


@pytest.mark.parametrize('command', ['open Chrome and Notepad', 'open Chrome https://example.com', 'open https://example.com https://other.test', 'reopen chrome', 'how do I open chrome?', 'open chromeium', 'opener chrome', 'open chrome and then volume 100'])
def test_ambiguous_or_compound_commands_do_not_dispatch(tmp_path, command):
    tools = Tools()
    engine = Engine(Settings(), Memory(tmp_path/'db'), tools)
    assert not engine.execute(command).ok
    assert not tools.calls


@pytest.mark.parametrize('command,app', [('open Chrome', 'chrome'), ('Mera Chrome kholo', 'chrome'), ('क्रोम खोलो','chrome'), ('ਕ੍ਰੋਮ ਖੋਲ','chrome'), ('open File Explorer','explorer'), ('Notepad khol do','notepad')])
def test_supported_whole_command_intents(command, app):
    assert app_intent(command) == app


def test_filename_queries_do_not_route_as_app_or_diagnostics(tmp_path):
    tools = Tools()
    (tmp_path/'open-chrome-report.txt').write_text('test')
    (tmp_path/'cpu-report.txt').write_text('test')
    engine = Engine(Settings(approved_folders=[str(tmp_path)]), Memory(tmp_path/'db'), tools)
    assert 'open-chrome-report.txt' in engine.execute('find open-chrome-report').message
    assert 'cpu-report.txt' in engine.execute('find cpu-report').message
    assert not tools.calls


def test_ambiguous_open_step_rejected_before_any_workflow_dispatch(tmp_path):
    tools = Tools()
    settings = Settings(workflows={'bad': ['open Notepad', 'open Chrome and Notepad']})
    engine = Engine(settings, Memory(tmp_path/'db'), tools)
    assert not engine.execute('run workflow bad').ok
    assert tools.calls == []


def test_cancel_after_submit_before_worker_dispatch_is_preserved(tmp_path):
    tools = Tools()
    engine = Engine(Settings(), Memory(tmp_path/'db'), tools)
    engine.cancelled.clear()  # UI accepts a new command before scheduling.
    engine.cancelled.set()  # User cancels before the worker begins.
    result = engine.execute('open Chrome', reset_cancellation=False)
    assert not result.ok and 'cancelled before execution' in result.message
    assert tools.calls == []
    assert engine.execute('open Chrome').ok  # A new independent command resets cancellation.
    assert tools.calls == ['chrome']
