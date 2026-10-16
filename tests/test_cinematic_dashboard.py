"""Exercise redesigned controls through the real controller and permission engine."""
import os
import subprocess
import sys

import pytest


def test_quick_commands_preserve_engine_permissions_and_store_real_notes():
    pytest.importorskip("PySide6")
    script = r'''
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication, QMessageBox, QInputDialog
from PySide6.QtCore import QTimer, QEventLoop
from sidhu.app import desktop
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory

class Tools:
    def __init__(self): self.calls = []
    def launch(self, name):
        self.calls.append(name)
        return 'Dispatched ' + name
    def website(self, url):
        self.calls.append(url)
        return 'Dispatched browser'

original = QApplication.exec
outcome = []
def run(self):
    window = next(w for w in self.topLevelWidgets() if hasattr(w, 'dispatch'))
    def wait_task():
        loop = QEventLoop()
        timer = QTimer()
        timer.timeout.connect(lambda: loop.quit() if not window.busy else None)
        timer.start(10)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()
        assert not window.busy
    assert window.voice.thread is None
    assert window.visual.fallback is not None
    assert window.render_label.text() == 'ANIMATED 2D'
    assert window.waveform._level == 0
    assert not window.log.isVisible()
    window.feed_toggle.click()
    assert window.log.isVisible()
    window.quick_buttons['Open Chrome'].click()
    wait_task()
    assert tools.calls == ['chrome']
    assert 'Dispatched chrome' in window.bubble.message.text()
    settings.allowed_apps = []
    window.quick_buttons['Open Chrome'].click()
    wait_task()
    assert tools.calls == ['chrome']
    assert 'not allowed' in window.bubble.message.text()
    notices = []
    QMessageBox.information = lambda *args: notices.append(args[2])
    window.quick_buttons['Write a note'].click()
    assert not engine.memory.path.exists()
    assert 'Enable explicit note memory' in notices[-1]
    settings.memory_enabled = True
    QInputDialog.getMultiLineText = lambda *args: ('A real local note', True)
    window.quick_buttons['Write a note'].click()
    wait_task()
    assert engine.memory.list() == [(1, 'A real local note')]
    QInputDialog.getText = lambda *args: ('Punjabi music & culture', True)
    window.quick_buttons['Search on Google'].click()
    wait_task()
    assert tools.calls[-1] == 'https://www.google.com/search?q=Punjabi+music+%26+culture'
    window.quick_buttons['Tell me the time'].click()
    wait_task()
    assert 'It is ' in window.bubble.message.text()
    before = list(tools.calls)
    window.dispatch('shutdown PC')
    wait_task()
    assert tools.calls == before
    assert 'not recognized' in window.bubble.message.text()
    # Delayed Qt events from utterance A must not affect utterance B.
    window.speaker.utterance_id += 1
    stale = window.speaker.utterance_id
    window.speaker.utterance_id += 1
    current = window.speaker.utterance_id
    window.voice.speaking.set()
    window.update_activity()
    before = window.visual._viseme_serial
    bubble_before = window.bubble.message.text()
    window.events.speech_viseme.emit(stale, 2, 500)
    window.events.speech_text.emit(stale, 'Stale utterance')
    assert window.visual._viseme_serial == before
    assert window.bubble.message.text() == bubble_before
    window.events.speech_viseme.emit(current, 2, 500)
    assert window.visual._viseme_serial == before + 1
    window.events.speech_text.emit(current, 'Current utterance')
    assert window.bubble.message.text() == 'Current utterance'
    window.voice.speaking.clear()
    window.update_activity()
    window.events.speech_viseme.emit(current, 2, 500)
    assert window.visual._viseme_serial == before + 1
    window.voice.state = 'listening'
    window.listener_generation = 8
    window.events.input_level.emit(7, .9)
    assert window.waveform._level == 0
    window.events.input_level.emit(8, .2)
    assert window.waveform._level == .2
    window.voice.state = 'muted'
    window.voice_changed('muted')
    assert window.waveform._level == 0
    window.resize(1280, 800)
    QApplication.processEvents()
    assert window.entry.isVisible() and window.mic_button.isVisible()
    assert window.width() == 1280 and window.height() == 800
    assert window.entry.geometry().width() > 200
    window.resize(1366, 728)
    QApplication.processEvents()
    assert window.height() == 728
    assert window.session_dialog.isVisible()
    window.session_dialog.reject()
    assert not window.feed_toggle.isChecked()
    outcome.append(True)
    QTimer.singleShot(0, window.quit)
    return original()
QApplication.exec = run
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(speech_enabled=False)
    tools = Tools()
    engine = Engine(settings, Memory(root/'memory.sqlite3'), tools)
    desktop(settings, engine, root, False)
assert outcome == [True]
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_packaging_smoke_saves_actual_window_without_audio(tmp_path):
    pytest.importorskip("PySide6")
    preview = tmp_path / "desktop.png"
    result = subprocess.run(
        [sys.executable, "-m", "sidhu.app", "--ui-smoke"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "SIDHU_DATA_DIR": str(tmp_path / "data"), "SIDHU_UI_PREVIEW": str(preview)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SIDHU_UI_SMOKE_OK" in result.stdout
    assert preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
