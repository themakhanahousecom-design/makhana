import json
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory


class Windows:
    def __init__(self):
        self.calls = []
    def list_windows(self):
        self.calls.append('list')
        return [{'hwnd': 10, 'title': 'My exact title', 'pid': 50}]
    def action(self, title, state):
        self.calls.append((title, state))
        return 'Observed state verified by test backend'


def test_permission_blocks_listing_and_actions(tmp_path):
    windows = Windows()
    engine = Engine(Settings(), Memory(tmp_path/'db'), window_controller=windows)
    assert not engine.execute('windows').ok
    assert not engine.execute('window minimize My exact title').ok
    assert windows.calls == []


def test_enabled_commands_preserve_exact_title_and_action(tmp_path):
    windows = Windows()
    engine = Engine(Settings(window_control_enabled=True), Memory(tmp_path/'db'), window_controller=windows)
    result = engine.execute('windows')
    assert result.ok and json.loads(result.message)[0]['title'] == 'My exact title'
    assert engine.execute('window MINIMIZE "My exact title"').ok
    assert windows.calls == ['list', ('My exact title', 'minimize')]
    assert not engine.execute('window close My exact title').ok
    assert len(windows.calls) == 2


def test_window_titles_are_not_persisted_in_activity_metadata(tmp_path):
    windows = Windows()
    engine = Engine(Settings(window_control_enabled=True, history_enabled=True), Memory(tmp_path/'db'), window_controller=windows)
    assert engine.execute('window switch private-sensitive-title').ok
    history = engine.activity.path.read_bytes()
    assert b'private-sensitive-title' not in history
    assert engine.activity.list()[0][1] == 'window switch'


def test_supervisor_status_never_claims_live_health(tmp_path):
    engine = Engine(Settings(), Memory(tmp_path/'db'))
    result = engine.execute('supervisor status')
    assert result.ok
    status = json.loads(result.message)
    assert not status['available'] and 'not a live' in status['note']
