"""Screen capture uses generated QImages only; never grabs a physical screen."""
import builtins
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from sidhu.screen import MAX_PNG_BYTES, CapturedScreen, ScreenCaptureService


def test_confirmation_refuses_before_backend_or_qt_import(monkeypatch):
    calls = []
    original_import = builtins.__import__

    def forbid_qt(name, *args, **kwargs):
        assert not name.startswith('PySide6'), 'Qt imported before capture confirmation'
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbid_qt)
    service = ScreenCaptureService(lambda: calls.append('capture'))
    for confirmation in (False, None, 1, 'yes'):
        with pytest.raises(PermissionError, match='explicit confirmation'):
            service.capture(confirmed=confirmation)
    assert calls == []


def test_module_import_does_not_require_desktop_extra():
    result = subprocess.run([sys.executable, '-c', '''
import builtins
original = builtins.__import__
def without_qt(name, *args, **kwargs):
    if name.startswith('PySide6'):
        raise ImportError('desktop extra not installed')
    return original(name, *args, **kwargs)
builtins.__import__ = without_qt
from sidhu.screen import ScreenCaptureService
service = ScreenCaptureService()
try:
    service.capture(confirmed=True)
except RuntimeError as error:
    assert 'desktop extra' in str(error)
else:
    raise AssertionError('Missing desktop extra was not reported')
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def image_types():
    pytest.importorskip('PySide6')
    from PySide6.QtGui import QColor, QImage
    return QImage, QColor


@pytest.mark.parametrize('dimensions,expected', [
    ((800, 600), (800, 600)),
    ((4096, 2048), (2048, 1024)),
    ((1024, 4096), (512, 2048)),
    ((4001, 2000), (2048, 1023)),
])
def test_capture_encodes_real_png_and_preserves_aspect(image_types, dimensions, expected):
    QImage, QColor = image_types
    original = QImage(*dimensions, QImage.Format.Format_RGB32)
    original.fill(QColor('navy'))
    calls = []

    def backend():
        calls.append('capture')
        return original

    capture = ScreenCaptureService(backend).capture(confirmed=True)
    assert isinstance(capture, CapturedScreen)
    assert (capture.width, capture.height) == expected
    assert capture.png.startswith(b'\x89PNG\r\n\x1a\n')
    assert len(capture.png) <= MAX_PNG_BYTES
    decoded = QImage.fromData(capture.png, 'PNG')
    assert not decoded.isNull()
    assert (decoded.width(), decoded.height()) == expected
    assert decoded.pixelColor(0, 0).name() == '#000080'
    assert (original.width(), original.height()) == dimensions
    assert calls == ['capture']


def test_capture_never_opens_a_file_or_creates_outputs(image_types, monkeypatch, tmp_path):
    QImage, QColor = image_types
    source = QImage(30, 20, QImage.Format.Format_RGB32)
    source.fill(QColor('red'))
    monkeypatch.chdir(tmp_path)

    def deny_file_open(*args, **kwargs):
        raise AssertionError('Screen capture must stay in memory')

    monkeypatch.setattr(builtins, 'open', deny_file_open)
    monkeypatch.setattr(Path, 'open', deny_file_open)
    captured = ScreenCaptureService(lambda: source).capture(confirmed=True)
    assert captured.png
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', [None, b'not an image'])
def test_unusable_backend_result_is_clear(image_types, value):
    with pytest.raises(RuntimeError, match='no usable image'):
        ScreenCaptureService(lambda: value).capture(confirmed=True)


def test_null_image_is_rejected(image_types):
    QImage, _ = image_types
    with pytest.raises(RuntimeError, match='no usable image'):
        ScreenCaptureService(QImage).capture(confirmed=True)


def test_input_pixel_limit_is_checked_before_scaling(image_types, monkeypatch):
    from sidhu import screen
    QImage, _ = image_types
    source = QImage(20, 20, QImage.Format.Format_RGB32)
    monkeypatch.setattr(screen, 'MAX_PIXELS', 399)
    with pytest.raises(RuntimeError, match='40 million pixel'):
        ScreenCaptureService(lambda: source).capture(confirmed=True)


def test_encoded_size_limit_is_enforced(image_types, monkeypatch):
    from sidhu import screen
    QImage, QColor = image_types
    source = QImage(30, 20, QImage.Format.Format_RGB32)
    source.fill(QColor('blue'))
    monkeypatch.setattr(screen, 'MAX_PNG_BYTES', 10)
    with pytest.raises(RuntimeError, match='4 MiB PNG limit'):
        ScreenCaptureService(lambda: source).capture(confirmed=True)


def test_native_capture_requires_gui_application_without_grabbing_screen(image_types):
    # No Qt application exists in this process; every other fixture uses QImage.
    with pytest.raises(RuntimeError, match='running Qt desktop application'):
        ScreenCaptureService().capture(confirmed=True)


@pytest.mark.parametrize('availability', ['missing_screen', 'null_pixmap', 'image'])
def test_native_capture_handles_screen_availability(image_types, monkeypatch, availability):
    from PySide6 import QtCore, QtGui
    QImage, QColor = image_types
    source = QImage(40, 30, QImage.Format.Format_RGB32)
    source.fill(QColor('green'))
    calls = []

    class FakePixmap:
        def isNull(self):
            return availability == 'null_pixmap'

        def width(self):
            return source.width()

        def height(self):
            return source.height()

        def toImage(self):
            return source

    def grab(window_id):
        calls.append(window_id)
        return FakePixmap()

    class FakeApplication:
        @staticmethod
        def instance():
            return FakeApplication()

        def thread(self):
            return QtCore.QThread.currentThread()

        def primaryScreen(self):
            return None if availability == 'missing_screen' else SimpleNamespace(grabWindow=grab)

    monkeypatch.setattr(QtGui, 'QGuiApplication', FakeApplication)
    if availability == 'image':
        captured = ScreenCaptureService().capture(confirmed=True)
        assert (captured.width, captured.height) == (40, 30)
    else:
        message = 'No primary screen' if availability == 'missing_screen' else 'capture is unavailable'
        with pytest.raises(RuntimeError, match=message):
            ScreenCaptureService().capture(confirmed=True)
    assert calls == ([] if availability == 'missing_screen' else [0])


def test_native_capture_rejects_worker_thread_before_grabbing_screen(image_types):
    result = subprocess.run([sys.executable, '-c', '''
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import threading
from PySide6.QtGui import QGuiApplication
from sidhu.screen import ScreenCaptureService
app = QGuiApplication([])
errors = []
def worker():
    try:
        ScreenCaptureService().capture(confirmed=True)
    except RuntimeError as error:
        errors.append(str(error))
thread = threading.Thread(target=worker)
thread.start()
thread.join(timeout=5)
assert errors and 'GUI thread' in errors[0], errors
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
