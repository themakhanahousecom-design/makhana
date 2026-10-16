"""Actual Qt approval/preview flow with generated images and controlled HTTP transport."""
import os
import subprocess
import sys
import pytest


@pytest.mark.parametrize('scenario', ['capture_denied', 'discard_preview', 'share_denied', 'share_approved', 'cancel_preview', 'disabled', 'provider_changed'])
def test_capture_preview_and_separate_sharing_permission(scenario):
    pytest.importorskip('PySide6')
    script = r'''
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import tempfile
import sys
import httpx
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QDialog, QPushButton, QMessageBox
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
from sidhu.screen import ScreenCaptureService
from sidhu.screen_ui import ScreenWorkflow
scenario = sys.argv[1]
app = QApplication([])
class Owner(QWidget):
    busy = False
    exiting = False
    def __init__(self):
        super().__init__()
        self.task_status = QLabel(self)
    def update_activity(self):
        pass
owner = Owner()
owner.show()
logs, captured, requests, results = [], [], [], []
image = QImage(80, 60, QImage.Format_RGB32)
image.fill(0x00234567)
def backend():
    captured.append(1)
    return image
original_client = httpx.Client
def handler(request):
    requests.append(json.loads(request.content))
    return httpx.Response(200, json={'choices': [{'message': {'content': 'Visual response'}}]})
httpx.Client = lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs)
QMessageBox.question = lambda *args: QMessageBox.No if scenario == 'capture_denied' else QMessageBox.Yes
QMessageBox.information = lambda *args: QMessageBox.Ok
QMessageBox.exec = lambda self: QMessageBox.No if scenario == 'share_denied' else QMessageBox.Yes
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = Settings(screen_capture_enabled=scenario != 'disabled', ai_model='image-model', ai_base_url='https://vision.test/v1')
    engine = Engine(settings, Memory(root/'notes.db'))
    pool = ThreadPoolExecutor(max_workers=1)
    def done(result):
        results.append(result)
        owner.busy = False
    flow = ScreenWorkflow(owner, settings, engine, pool, done, logs.append, service=ScreenCaptureService(backend))
    interacted = []
    def interact():
        dialog = app.activeModalWidget()
        if isinstance(dialog, QDialog) and dialog.windowTitle().startswith('One-shot screen preview') and not interacted:
            interacted.append(1)
            buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
            if scenario == 'discard_preview':
                buttons['Discard image'].click()
            elif scenario == 'cancel_preview':
                engine.cancelled.set()
            else:
                if scenario == 'provider_changed':
                    engine.ai.reconfigure(base_url='https://new.test/v1', model='new', key_env='OTHER_KEY', keep_context=False)
                buttons['Approve image analysis…'].click()
                if scenario == 'share_denied':
                    buttons['Discard image'].click()
    timer = QTimer()
    timer.timeout.connect(interact)
    timer.start(20)
    finished = []
    def check():
        if not flow.active and not owner.busy:
            finished.append(1)
            app.quit()
    completion = QTimer()
    completion.timeout.connect(check)
    completion.start(20)
    QTimer.singleShot(0, flow.begin)
    QTimer.singleShot(5000, app.quit)
    app.exec()
    pool.shutdown(wait=True)
    assert finished == [1], (scenario, logs, owner.task_status.text())
    assert len(captured) == (0 if scenario in {'capture_denied','disabled'} else 1)
    assert len(requests) == (1 if scenario == 'share_approved' else 0)
    if scenario == 'share_approved':
        assert len(results) == 1 and results[0].ok
        assert requests[0]['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
    elif scenario == 'provider_changed':
        assert len(results) == 1 and not results[0].ok
    else:
        assert results == []
    assert engine.ai._turns == []
    assert list(root.iterdir()) == []
'''
    result = subprocess.run([sys.executable, '-c', script, scenario], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
