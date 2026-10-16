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


def test_live_viseme_shapes_and_cancel_reset_in_actual_qml_component():
    run_qt('''
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlEngine, QQmlComponent
from PySide6.QtCore import QUrl
from pathlib import Path
import sidhu
app = QGuiApplication([])
engine = QQmlEngine()
context = engine.rootContext()
for name, value in [('assistantState','speaking'),('assistantWordSerial',0),
                    ('assistantVisible',False),('assistantViseme',0),
                    ('assistantVisemeSerial',0),('assistantVisemeDuration',200)]:
    context.setContextProperty(name, value)
component = QQmlComponent(engine, QUrl.fromLocalFile(str(Path(sidhu.__file__).parent/'assets/avatar.qml')))
root = component.create()
assert root is not None, [error.toString() for error in component.errors()]
context.setContextProperty('assistantViseme', 2)
context.setContextProperty('assistantVisemeSerial', 1)
assert root.property('mouthOpen') > .7
assert abs(root.property('mouthWidth') - .9) < .001
assert root.property('lipSyncMode') == 'viseme'
context.setContextProperty('assistantViseme', 21)
context.setContextProperty('assistantVisemeSerial', 2)
assert root.property('mouthOpen') == 0
context.setContextProperty('assistantViseme', 2)
context.setContextProperty('assistantVisemeSerial', 3)
context.setContextProperty('assistantState', 'muted')
assert root.property('mouthOpen') == 0
assert root.property('lipSyncMode') == 'idle'
root.deleteLater()
''')


def test_original_portrait_renders_animates_and_rejects_inactive_speech():
    run_qt('''
from PySide6.QtWidgets import QApplication
from sidhu.avatar import AvatarView
from sidhu.avatar_portrait import MOUTH_SHAPES
app = QApplication([])
view = AvatarView(enabled=False)
view.resize(600, 700)
view.show()
app.processEvents()
portrait = view.fallback
assert portrait.artwork_source == 'original rendered portrait'
assert not view.grab().isNull()
assert portrait.timer.isActive()
view.activity = 'speaking'
view.viseme(2, 100)
assert portrait._mouth == MOUTH_SHAPES[2]
serial = view._viseme_serial
view.activity = 'muted'
view.viseme(2, 100)
assert view._viseme_serial == serial
view.set_performance(True)
portrait._mouth_until = 0
portrait._tick()
assert not portrait.timer.isActive()
view.set_performance(False)
assert portrait.timer.isActive()
view.hide()
assert not portrait.timer.isActive()
''')
