import pytest
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
from sidhu.workflows import validate_workflows


class Tools:
    def __init__(self):
        self.calls = []
    def launch(self, name):
        self.calls.append(name)
        return 'dispatch accepted'


def make_engine(tmp_path, steps):
    settings = Settings(workflows={'work setup': steps})
    tools = Tools()
    progress = []
    return Engine(settings, Memory(tmp_path / 'db'), tools, on_progress=progress.append), tools, progress


def test_sequential_workflow_and_progress(tmp_path):
    engine, tools, progress = make_engine(tmp_path, ['open Chrome', 'open Notepad'])
    result = engine.execute('run workflow Work Setup')
    assert result.ok
    assert tools.calls == ['chrome', 'notepad']
    assert len(progress) == 2 and '2/2' in progress[1]
    assert 'dispatch limitations' in result.message


def test_failure_stops_remaining_steps(tmp_path):
    engine, tools, progress = make_engine(tmp_path, ['open Chrome', 'open Notepad'])
    engine.settings.allowed_apps = ['notepad']
    result = engine.execute('run workflow work setup')
    assert not result.ok and 'failed step' in result.message
    assert not tools.calls and len(progress) == 1


def test_cancellation_preserved_between_steps(tmp_path):
    engine, tools, _ = make_engine(tmp_path, ['open Chrome', 'open Notepad'])
    def launch(name):
        tools.calls.append(name)
        engine.cancelled.set()
        return 'dispatched'
    tools.launch = launch
    result = engine.execute('run workflow work setup')
    assert not result.ok and 'cancelled' in result.message
    assert tools.calls == ['chrome']


@pytest.mark.parametrize('value', [[], {'x': []}, {'x': ['run workflow x']}, {'x': ['ask open chrome']}, {'x': ['remember note']}, {'x': ['powershell whoami']}, {'x': ['open Chrome'] * 11}, {'A': ['battery'], 'a': ['battery']}])
def test_workflow_schema_rejects_unsupported_or_unbounded_plans(value):
    with pytest.raises(ValueError):
        validate_workflows(value)


def test_workflows_persist(tmp_path):
    path = tmp_path / 'settings.json'
    settings = Settings(workflows=validate_workflows({'Work Setup': ['diagnostics']}))
    settings.save(path)
    assert Settings.load(path).workflows == {'work setup': ['diagnostics']}


def test_workflow_url_diagnostics_does_not_misroute(tmp_path):
    engine, tools, _ = make_engine(tmp_path, ['inspect https://example.com/performance'])
    result = engine.execute('run workflow work setup')
    assert not result.ok and 'disabled' in result.message
    assert tools.calls == []
