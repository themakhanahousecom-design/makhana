"""QML structure/bindings and software fallback; no GPU-rendering claim."""
import os
import subprocess
import sys
import pytest


def run_qt(script):
    pytest.importorskip('PySide6')
    result = subprocess.run([sys.executable, '-c', script], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'}, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_avatar_scene_instantiates_and_tracks_real_state_bindings():
    run_qt('''
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtCore import QUrl
from pathlib import Path
import sidhu
app = QGuiApplication([])
engine = QQmlEngine()
context = engine.rootContext()
for name, value in [('assistantState','listening'),('assistantWordSerial',0),('assistantVisible',False)]:
    context.setContextProperty(name, value)
component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(sidhu.__file__).parent/'assets/avatar.qml')))
root = component.create()
assert root is not None, [error.toString() for error in component.errors()]
assert root.property('activity') == 'listening'
context.setContextProperty('assistantState','speaking')
context.setContextProperty('assistantWordSerial',1)
assert root.property('activity') == 'speaking'
assert root.property('wordSerial') == 1
assert not root.property('animating')
root.deleteLater()
''')


def test_software_renderer_falls_back_instead_of_blank_3d_scene():
    run_qt('''
from PySide6.QtWidgets import QApplication, QLabel
from sidhu.avatar import AvatarView
app = QApplication([])
widget = AvatarView(lambda: QLabel('CORE FALLBACK'), enabled=True)
assert widget.fallback is not None
widget.activity = 'error'
assert widget.fallback.activity == 'error'
widget.show()
app.processEvents()
assert widget.fallback.isVisible()
assert widget.quick.isHidden()
widget.hide()
''')
