"""Explicitly enabled local tasks/reminders. No calendar or messaging service is implied."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import time


class Productivity:
    def __init__(self, path: Path, enabled, clock=time.time):
        self.path, self.enabled, self.clock = path, enabled, clock

    @contextmanager
    def connect(self):
        if not self.enabled():
            raise RuntimeError('Local tasks and reminders are disabled. Enable productivity in Settings.')
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, body TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)')
                db.execute("CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY, body TEXT NOT NULL, due REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending')")
                yield db
        finally:
            db.close()

    @staticmethod
    def validate_text(text):
        text = text.strip()
        if not text or len(text) > 4000:
            raise ValueError('Supply 1–4,000 characters of text.')
        return text

    def add_task(self, text):
        text = self.validate_text(text)
        with self.connect() as db:
            count = db.execute('SELECT count(*) FROM tasks').fetchone()[0]
            if count >= 10000:
                raise ValueError('Task limit reached (10,000). No task was added.')
            return db.execute('INSERT INTO tasks(body) VALUES (?)', (text,)).lastrowid

    def tasks(self):
        with self.connect() as db:
            return db.execute('SELECT id, body, done FROM tasks ORDER BY done, id DESC LIMIT 200').fetchall()

    def set_done(self, task_id, done=True):
        with self.connect() as db:
            if db.execute('UPDATE tasks SET done=? WHERE id=?', (int(done), task_id)).rowcount != 1:
                raise ValueError('Task does not exist.')

    def add_reminder(self, minutes, text):
        if not isinstance(minutes, int) or not 1 <= minutes <= 525600:
            raise ValueError('Reminder delay must be 1–525,600 minutes.')
        text = self.validate_text(text)
        due = self.clock() + minutes * 60
        with self.connect() as db:
            count = db.execute('SELECT count(*) FROM reminders').fetchone()[0]
            if count >= 10000:
                raise ValueError('Reminder limit reached (10,000). No reminder was added.')
            reminder_id = db.execute('INSERT INTO reminders(body,due) VALUES (?,?)', (text, due)).lastrowid
        return reminder_id, due

    def reminders(self):
        with self.connect() as db:
            return db.execute('SELECT id, body, due, state FROM reminders ORDER BY due DESC LIMIT 200').fetchall()

    def cancel_reminder(self, reminder_id):
        with self.connect() as db:
            if db.execute("UPDATE reminders SET state='cancelled' WHERE id=? AND state='pending'", (reminder_id,)).rowcount != 1:
                raise ValueError('Pending reminder does not exist.')

    def due(self):
        with self.connect() as db:
            return db.execute("SELECT id, body, due FROM reminders WHERE state='pending' AND due <= ? ORDER BY due LIMIT 20", (self.clock(),)).fetchall()

    def mark_dispatched(self, reminder_id):
        with self.connect() as db:
            db.execute("UPDATE reminders SET state='dispatched' WHERE id=? AND state='pending'", (reminder_id,))

    def clear(self):
        with self.connect() as db:
            db.execute('DELETE FROM tasks')
            db.execute('DELETE FROM reminders')


def format_time(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')


class ReminderScheduler:
    """Single desktop instance only. Callback success means dispatch, not human receipt."""
    def __init__(self, store, notify, on_error=lambda text: None):
        self.store, self.notify, self.on_error = store, notify, on_error

    def tick(self):
        if not self.store.enabled():
            return
        try:
            for reminder_id, body, due in self.store.due():
                try:
                    self.notify(reminder_id, body, due)
                    self.store.mark_dispatched(reminder_id)
                except Exception:
                    self.on_error(f'Reminder {reminder_id} could not be dispatched; retained for retry.')
        except Exception:
            self.on_error('Reminder storage is unavailable; delivery will be retried.')
