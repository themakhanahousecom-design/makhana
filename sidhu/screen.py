"""One-shot, explicitly confirmed screen capture kept only in memory.

Qt is imported only when a confirmed capture is requested, so the command-line
package remains usable without the desktop extra. This service does not send
the returned image anywhere; the caller owns any separate sharing decision.
"""
from dataclasses import dataclass


MAX_DIMENSION = 2048
MAX_PIXELS = 40_000_000
MAX_PNG_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CapturedScreen:
    png: bytes
    width: int
    height: int


class ScreenCaptureService:
    def __init__(self, backend=None):
        self._backend = backend

    def capture(self, *, confirmed=False) -> CapturedScreen:
        # Check before importing Qt, touching the desktop, or invoking a backend.
        if confirmed is not True:
            raise PermissionError('Screen capture requires explicit confirmation for this capture.')
        try:
            from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
            from PySide6.QtGui import QImage
        except ImportError as exc:
            raise RuntimeError('Screen capture requires the desktop extra (PySide6).') from exc

        image = self._backend() if self._backend is not None else self._capture_primary_screen()
        if not isinstance(image, QImage) or image.isNull():
            raise RuntimeError('Screen capture returned no usable image. Check the desktop session and screen permissions.')
        width, height = image.width(), image.height()
        self._check_dimensions(width, height)
        if max(width, height) > MAX_DIMENSION:
            image = image.scaled(MAX_DIMENSION, MAX_DIMENSION, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            if image.isNull():
                raise RuntimeError('The captured screen could not be resized.')

        encoded = QByteArray()
        buffer = QBuffer(encoded)
        if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
            raise RuntimeError('Could not create an in-memory screen image buffer.')
        try:
            if not image.save(buffer, 'PNG'):
                raise RuntimeError('The captured screen could not be encoded as PNG.')
        finally:
            buffer.close()
        if encoded.size() > MAX_PNG_BYTES:
            raise RuntimeError('The captured screen exceeds the 4 MiB PNG limit. No image was retained or shared.')
        return CapturedScreen(bytes(encoded), image.width(), image.height())

    @staticmethod
    def _check_dimensions(width, height):
        if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
            raise RuntimeError('The captured screen dimensions exceed the supported 40 million pixel limit.')

    @classmethod
    def _capture_primary_screen(cls):
        from PySide6.QtCore import QThread
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if not isinstance(app, QGuiApplication):
            raise RuntimeError('Screen capture requires a running Qt desktop application.')
        if QThread.currentThread() != app.thread():
            raise RuntimeError('Screen capture must run on the Qt GUI thread.')
        screen = app.primaryScreen()
        if screen is None:
            raise RuntimeError('No primary screen is available for capture in this desktop session.')
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            raise RuntimeError('Screen capture is unavailable. Check the desktop session and screen permissions.')
        # Check before allocating the QImage copy of a native screen pixmap.
        cls._check_dimensions(pixmap.width(), pixmap.height())
        return pixmap.toImage()
