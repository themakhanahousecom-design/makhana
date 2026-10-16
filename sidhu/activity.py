"""Opt-in execution metadata only. Never persists command arguments or tool output."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class Activity:
    def __init__(self, path: Path, enabled):
        self.path, self.enabled = path, enabled

    @contextmanager
    def connect(self):
        if not self.enabled():
            raise RuntimeError('Activity history is disabled. Enable it in Settings to store execution metadata.')
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS activity (id INTEGER PRIMARY KEY, at TEXT NOT NULL, operation TEXT NOT NULL, agent TEXT NOT NULL, ok INTEGER NOT NULL, elapsed_ms REAL NOT NULL)')
                yield db
        finally:
            db.close()

    def append(self, operation, agent, ok, elapsed_ms):
        if not self.enabled():
            return
        with self.connect() as db:
            db.execute('INSERT INTO activity(at,operation,agent,ok,elapsed_ms) VALUES (?,?,?,?,?)', (datetime.now(timezone.utc).isoformat(), operation, agent, int(ok), elapsed_ms))
            db.execute('DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT 500)')

    def list(self):
        with self.connect() as db:
            return db.execute('SELECT at, operation, agent, ok, elapsed_ms FROM activity ORDER BY id DESC LIMIT 200').fetchall()

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM activity')


def operation_label(command):
    """Return only labels from this source code, never interpolate user text."""
    value = command.casefold().strip()
    for prefix in ('window minimize ', 'window maximize ', 'window restore ', 'window switch ', 'summarize file ', 'analyze csv ', 'document ', 'run workflow ', 'task add ', 'task done ', 'task reopen ', 'remind in ', 'cancel reminder ', 'read ', 'search text ', 'inspect ', 'remember ', 'ask ', 'find ', 'volume '):
        if value.startswith(prefix):
            return prefix.strip()
    known = {'capture screen', 'analyze screen', 'supervisor status', 'windows', 'ai models', 'new conversation', 'history', 'hardware', 'processes', 'diagnostics', 'battery', 'workflows', 'tasks', 'reminders', 'memories', 'recent files', 'duplicates', 'latest pdf', 'help', 'commands', 'cancel', 'stop'}
    if value in known:
        return value
    # No inferred free-form operation text is ever stored.
    return 'other command'
