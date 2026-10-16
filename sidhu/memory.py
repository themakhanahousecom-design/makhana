from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Memory:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
                yield db
        finally:
            db.close()

    def add(self, text: str):
        if not text.strip():
            raise ValueError('Note text cannot be empty.')
        with self._connect() as db:
            db.execute('INSERT INTO notes(body) VALUES (?)', (text,))

    def list(self):
        with self._connect() as db:
            return db.execute('SELECT id, body FROM notes ORDER BY id DESC').fetchall()

    def clear(self):
        with self._connect() as db:
            db.execute('DELETE FROM notes')

    def search(self, query):
        with self._connect() as db:
            return db.execute('SELECT id, body FROM notes WHERE instr(lower(body), lower(?)) > 0 ORDER BY id DESC', (query,)).fetchall()

    def update(self, note_id, text):
        if not text.strip():
            raise ValueError('Note text cannot be empty.')
        with self._connect() as db:
            cursor = db.execute('UPDATE notes SET body = ? WHERE id = ?', (text, note_id))
            if cursor.rowcount != 1:
                raise ValueError('Note no longer exists.')

    def delete(self, note_id):
        with self._connect() as db:
            cursor = db.execute('DELETE FROM notes WHERE id = ?', (note_id,))
            if cursor.rowcount != 1:
                raise ValueError('Note no longer exists.')
