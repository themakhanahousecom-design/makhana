import sqlite3
import pytest
from sidhu.activity import Activity, operation_label
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory


def test_disabled_activity_never_creates_database(tmp_path):
    store = Activity(tmp_path/'absent.db', lambda: False)
    store.append('diagnostics', 'Diagnostics', True, 1)
    with pytest.raises(RuntimeError, match='disabled'):
        store.list()
    assert not store.path.exists()


def test_activity_persists_metadata_but_no_command_or_output(tmp_path):
    engine = Engine(Settings(history_enabled=True, productivity_enabled=True), Memory(tmp_path/'notes.db'))
    secret_text = 'private-project-unique-value-123'
    result = engine.execute('task add ' + secret_text)
    assert result.ok and result.elapsed_ms >= 0
    entries = Activity(engine.activity.path, lambda: True).list()
    assert len(entries) == 1
    assert entries[0][1:4] == ('task add', 'Productivity', 1)
    assert secret_text.encode() not in engine.activity.path.read_bytes()
    assert 'task add' == operation_label('task add ' + secret_text)


def test_activity_retention_and_clear(tmp_path):
    store = Activity(tmp_path/'history.db', lambda: True)
    for i in range(505):
        store.append('diagnostics', 'Diagnostics', True, i)
    assert len(store.list()) == 200
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT count(*) FROM activity').fetchone()[0] == 500
    store.clear()
    assert store.list() == []


def test_history_storage_error_does_not_change_tool_result(tmp_path, monkeypatch):
    engine = Engine(Settings(history_enabled=True), Memory(tmp_path/'notes.db'))
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(engine.activity, 'append', fail)
    result = engine.execute('help')
    assert result.ok and result.history_warning
    assert 'Tool outcome is unchanged' in result.history_warning


def test_unknown_command_history_does_not_include_arbitrary_text(tmp_path):
    engine = Engine(Settings(history_enabled=True), Memory(tmp_path/'notes.db'))
    result = engine.execute('private arbitrary input')
    assert not result.ok
    assert engine.activity.list()[0][1] == 'other command'
