"""Optional least-privilege desktop watchdog; only launches this installed application."""
from collections import deque
from datetime import datetime, timezone
import json
import errno
import os
from pathlib import Path
import subprocess
import sys
import time

ALREADY_RUNNING = 20
MAX_RESTARTS = 3
RESTART_WINDOW_SECONDS = 300


class InstanceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None
        self.acquired = False

    def __enter__(self):
        self.stream = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.stream.write(b'\0')
            self.stream.flush()
        self.stream.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.acquired = True
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                self.stream.close()
                raise
            self.acquired = False
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            if self.acquired:
                self.stream.seek(0)
                if sys.platform == 'win32':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()


def child_command(*, background=False, recovering=False):
    command = [sys.executable]
    if not getattr(sys, 'frozen', False):
        command += ['-m', 'sidhu.app']
    command += ['--supervised-child']
    if background or recovering:
        command += ['--background']
    if recovering:
        command += ['--recovering']
    return command


def read_status(folder):
    path = Path(folder) / 'supervisor.json'
    if not path.exists():
        return {'available': False, 'note': 'No watchdog observations saved. This is not a live process-health check.'}
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Watchdog observations exceed the supported size.')
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get('events'), list) or len(data['events']) > 20:
        raise ValueError('Watchdog observations have an invalid format.')
    return {'available': True, 'note': 'Last saved watchdog observations only; not a live process-health check.', 'events': data['events']}


class Supervisor:
    def __init__(self, folder, *, spawn=subprocess.Popen, command_factory=child_command, clock=time.monotonic, wait=time.sleep):
        self.folder = Path(folder)
        self.spawn, self.command_factory, self.clock, self.wait = spawn, command_factory, clock, wait
        self.events = []

    def record(self, event, **fields):
        self.events.append({'at': datetime.now(timezone.utc).isoformat(), 'event': event, **fields})
        self.events = self.events[-20:]
        path = self.folder / 'supervisor.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'events': self.events}, indent=2), encoding='utf-8')
        temporary.replace(path)

    @staticmethod
    def _stop_child(child):
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

    def run(self, *, background=False):
        self.folder.mkdir(parents=True, exist_ok=True)
        with InstanceLock(self.folder / 'supervisor.lock') as lock:
            if not lock.acquired:
                return ALREADY_RUNNING
            crashes = deque()
            recovering = False
            while True:
                self.record('launch', recovering=recovering)
                child = None
                try:
                    child = self.spawn(self.command_factory(background=background, recovering=recovering), shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if sys.platform == 'win32' else 0)
                    code = child.wait()
                except KeyboardInterrupt:
                    self._stop_child(child)
                    self.record('interrupted')
                    return 130
                except Exception as exc:
                    self._stop_child(child)
                    self.record('launch_failed', error_type=type(exc).__name__)
                    return 1
                if code in {0, ALREADY_RUNNING}:
                    self.record('clean_exit' if code == 0 else 'desktop_already_running', exit_code=code)
                    return code
                now = self.clock()
                crashes.append(now)
                while crashes and now - crashes[0] > RESTART_WINDOW_SECONDS:
                    crashes.popleft()
                if len(crashes) > MAX_RESTARTS:
                    self.record('restart_budget_exhausted', exit_code=code)
                    return 1
                delay = min(2 ** (len(crashes) - 1), 10)
                self.record('restart_scheduled', exit_code=code, delay_seconds=delay, restart_number=len(crashes))
                try:
                    self.wait(delay)
                except KeyboardInterrupt:
                    self.record("interrupted")
                    return 130
                recovering = True
