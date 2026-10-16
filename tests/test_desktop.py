"""Headless Qt smoke test: proves a real command result reaches the dashboard."""
import os
from pathlib import Path
import subprocess
import sys
import pytest


def test_dashboard_real_command():
    pytest.importorskip('PySide6')
    script = r'''
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication, QDialog, QTextEdit, QDialogButtonBox, QPushButton, QListWidget, QInputDialog, QMessageBox, QFileDialog, QTableWidget
from PySide6.QtCore import QTimer
from sidhu.app import desktop
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
original = QApplication.exec
outcome = []
def test_exec(self):
    window = next(w for w in self.topLevelWidgets() if hasattr(w, 'dispatch'))
    window.log.append('<b>Literal tool output</b>')
    assert '<b>Literal tool output</b>' in window.log.toPlainText()
    def save_workflow():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        editor = dialog.findChild(QTextEdit)
        editor.setPlainText('{"test setup": ["diagnostics", "battery"]}')
        dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
    QTimer.singleShot(100, save_workflow)
    window.configure_workflows()
    assert engine.settings.workflows == {'test setup': ['diagnostics', 'battery']}
    assert Settings.load(root/'settings.json').workflows == engine.settings.workflows
    def close_settings():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QDialog)
        dialog.reject()
    QTimer.singleShot(100, close_settings)
    window.configure()
    engine.settings.memory_enabled = True
    engine.memory.add('original note')
    def manage_notes():
        dialog = QApplication.activeModalWidget()
        notes = dialog.findChild(QListWidget)
        notes.setCurrentRow(0)
        QInputDialog.getMultiLineText = lambda *args: ('updated note', True)
        buttons = {b.text(): b for b in dialog.findChildren(QPushButton)}
        buttons['Edit selected'].click()
        assert engine.memory.list() == [(1, 'updated note')]
        QFileDialog.getSaveFileName = lambda *args: (str(root/'export.json'), 'JSON (*.json)')
        buttons['Export all…'].click()
        import json
        assert json.loads((root/'export.json').read_text()) == [{'id': 1, 'text': 'updated note'}]
        notes.setCurrentRow(0)
        QMessageBox.question = lambda *args: QMessageBox.Yes
        buttons['Delete selected…'].click()
        assert engine.memory.list() == []
        buttons['Close'].click()
    QTimer.singleShot(100, manage_notes)
    window.manage_memory()
    engine.settings.productivity_enabled = True
    task_id = engine.productivity.add_task('GUI task')
    def manage_productivity():
        dialog = QApplication.activeModalWidget()
        tables = dialog.findChildren(QTableWidget)
        task_table = next(table for table in tables if table.columnCount() == 3)
        reminder_table = next(table for table in tables if table.columnCount() == 4)
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        task_table.selectRow(0)
        buttons['Done'].click()
        assert engine.productivity.tasks()[0][2] == 1
        task_table.selectRow(0)
        buttons['Reopen'].click()
        assert engine.productivity.tasks()[0][2] == 0
        QInputDialog.getMultiLineText = lambda *args: ('GUI reminder', True)
        QInputDialog.getInt = lambda *args: (5, True)
        buttons['Add reminder'].click()
        assert len(engine.productivity.reminders()) == 1
        reminder_table.selectRow(0)
        buttons['Cancel reminder'].click()
        assert engine.productivity.reminders()[0][3] == 'cancelled'
        buttons['Delete all…'].click()
        assert engine.productivity.tasks() == [] and engine.productivity.reminders() == []
        buttons['Close'].click()
    QTimer.singleShot(100, manage_productivity)
    window.manage_productivity()
    engine.productivity.clock = lambda: 1000
    reminder_id, _ = engine.productivity.add_reminder(1, 'GUI overdue notification')
    engine.productivity.clock = lambda: 1061
    window.scheduler.tick()
    assert 'GUI overdue notification' in window.log.toPlainText()
    assert engine.productivity.reminders()[0][3] == 'dispatched'
    engine.settings.ai_context_enabled = True
    engine.ai._turns = [{'role': 'user', 'content': 'temporary private context'}]
    cleared = engine.execute('new conversation')
    assert cleared.ok and engine.ai._turns == []
    engine.settings.history_enabled = True
    result = engine.execute('help')
    assert result.elapsed_ms >= 0
    def manage_activity():
        dialog = QApplication.activeModalWidget()
        table = dialog.findChild(QTableWidget)
        assert table.rowCount() == 1
        assert table.item(0, 1).text() == 'help'
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        buttons['Delete all…'].click()
        assert engine.activity.list() == []
        buttons['Close'].click()
    QTimer.singleShot(100, manage_activity)
    window.manage_activity()
    window.voice.stop_event.clear()
    window.voice._status('listening', 'Test listener state')
    window.listener_generation = 2
    window.dispatch_voice(1, 'task add stale voice event')
    assert engine.productivity.tasks() == []
    window.voice._status('error', 'Test microphone unavailable')
    window.dispatch('diagnostics')
    def verify():
        if window.busy:
            QTimer.singleShot(50, verify)
            return
        outcome.append('GiB' in window.log.toPlainText() and 'CPU' in window.stats.text() and window.status.text() == 'Test microphone unavailable' and window.visual.activity == 'error')
        window.quit()
    QTimer.singleShot(100, verify)
    QTimer.singleShot(10000, self.quit)
    return original()
QApplication.exec = test_exec
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(speech_enabled=False)
    engine = Engine(settings, Memory(root/'memory.db'))
    desktop(settings, engine, root, False)
assert outcome == [True], outcome
print('DASHBOARD_SMOKE_OK')
'''
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'DASHBOARD_SMOKE_OK' in result.stdout


def test_recovery_launch_keeps_microphone_muted():
    pytest.importorskip('PySide6')
    script = r'''
from pathlib import Path
import tempfile
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from sidhu.app import desktop
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
from sidhu.voice import VoiceService
original = QApplication.exec
outcome = []
def forbidden_start(self):
    raise AssertionError('Recovery must not start microphone capture')
VoiceService.start = forbidden_start
def run(self):
    window = next(widget for widget in self.topLevelWidgets() if hasattr(widget, 'dispatch'))
    def verify():
        outcome.append(window.voice.thread is None and 'Microphone muted' in window.status.text())
        window.quit()
    QTimer.singleShot(0, verify)
    return original()
QApplication.exec = run
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(speech_enabled=False)
    result = desktop(settings, Engine(settings, Memory(root/'notes.db')), root, True, recovering=True)
assert result == 0 and outcome == [True]
'''
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
