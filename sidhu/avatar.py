"""Original animated character with real 3D and an illustrated fallback."""
from pathlib import Path
import time
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class AvatarView(QWidget):
    mode_changed = Signal(str)

    def __init__(self, fallback_factory=None, enabled=True):
        super().__init__()
        self._activity = 'idle'
        self._words = 0
        self._viseme_serial = 0
        self._last_viseme = 0.0
        self._lightweight = False
        self._lip_sync_mode = 'idle'
        self.quick = None
        self.fallback = None
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.fallback_factory = fallback_factory
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(260, 340)
        if not enabled:
            self._fallback('Illustrated character · lightweight rendering')
            return
        try:
            from PySide6.QtQuickWidgets import QQuickWidget
            self.quick = QQuickWidget(self)
            self.quick.setClearColor(QColor(Qt.transparent))
            from PySide6.QtQuick import QSGRendererInterface
            api = self.quick.quickWindow().rendererInterface().graphicsApi()
            from PySide6.QtGui import QGuiApplication
            if api == QSGRendererInterface.GraphicsApi.Software or QGuiApplication.platformName() in ('offscreen', 'minimal'):
                self._fallback('Illustrated character · software rendering')
                return
            self.quick.setResizeMode(QQuickWidget.SizeRootObjectToView)
            self.quick.setMinimumHeight(320)
            context = self.quick.rootContext()
            context.setContextProperty('assistantState', self._activity)
            context.setContextProperty('assistantWordSerial', self._words)
            context.setContextProperty('assistantVisible', False)
            context.setContextProperty('assistantViseme', 0)
            context.setContextProperty('assistantVisemeSerial', 0)
            context.setContextProperty('assistantVisemeDuration', 100)
            context.setContextProperty('assistantLightweight', False)
            self.layout.addWidget(self.quick)
            self.quick.sceneGraphError.connect(lambda error, message: self._fallback('Illustrated character · 3D renderer unavailable'))
            self.quick.statusChanged.connect(self._status_changed)
            self.quick.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / 'assets' / 'avatar.qml')))
        except Exception:
            self._fallback('Illustrated character · 3D renderer unavailable')

    def _status_changed(self, status):
        from PySide6.QtQuickWidgets import QQuickWidget
        if status == QQuickWidget.Error:
            self._fallback('Illustrated character · 3D scene unavailable')

    def _fallback(self, message):
        if self.fallback is not None:
            return
        if self.quick is not None:
            self.quick.hide()
            self.quick.setSource(QUrl())
        if self.fallback_factory is None:
            from .avatar_portrait import TributePortrait
            self.fallback = TributePortrait()
        else:
            self.fallback = self.fallback_factory()
        self.fallback.activity = self._activity
        self.layout.addWidget(self.fallback, 1)
        if hasattr(self.fallback, 'set_performance'):
            self.fallback.set_performance(self._lightweight)
        notice = QLabel(message)
        self.notice = notice
        notice.setAlignment(Qt.AlignCenter)
        notice.setWordWrap(True)
        notice.setStyleSheet('color: #7194ac; font-size: 10px; padding: 2px; background: transparent;')
        self.layout.addWidget(notice)
        self.mode_changed.emit('illustrated')

    @property
    def render_mode(self):
        return 'illustrated' if self.fallback is not None else '3d'

    @property
    def lip_sync_mode(self):
        return self._lip_sync_mode

    @property
    def activity(self):
        return self._activity

    @activity.setter
    def activity(self, value):
        self._activity = value
        if value != 'speaking':
            self._lip_sync_mode = 'idle'
        if self.fallback is not None:
            self.fallback.activity = value
            self.fallback.update()
        elif self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantState', value)

    def set_performance(self, lightweight):
        """Pause decorative motion; retain speech-driven mouth positions."""
        self._lightweight = bool(lightweight)
        if self.fallback is not None and hasattr(self.fallback, 'set_performance'):
            self.fallback.set_performance(self._lightweight)
        if self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantLightweight', self._lightweight)

    def viseme(self, viseme_id, duration_ms=100):
        """Receive Microsoft SAPI's actual viseme ID (0–21), in milliseconds."""
        if self._activity != 'speaking':
            return
        if isinstance(viseme_id, bool) or not isinstance(viseme_id, int) or not 0 <= viseme_id <= 21:
            return
        try:
            duration_ms = max(20, min(1500, int(duration_ms)))
        except (TypeError, ValueError, OverflowError):
            duration_ms = 100
        self._viseme_serial += 1
        self._last_viseme = time.monotonic()
        self._lip_sync_mode = 'viseme'
        if self.fallback is not None and hasattr(self.fallback, 'viseme'):
            self.fallback.viseme(viseme_id, duration_ms)
        elif self.quick is not None and self.fallback is None:
            context = self.quick.rootContext()
            context.setContextProperty('assistantViseme', viseme_id)
            context.setContextProperty('assistantVisemeDuration', duration_ms)
            context.setContextProperty('assistantVisemeSerial', self._viseme_serial)

    def word(self, location=0, length=0):
        self._words += 1
        if self._activity == 'speaking' and time.monotonic() - self._last_viseme > 1.5:
            self._lip_sync_mode = 'word approximation'
        if self.fallback is not None and hasattr(self.fallback, 'word'):
            self.fallback.word(location, length)
        elif self.quick is not None and self.fallback is None:
            self.quick.rootContext().setContextProperty('assistantWordSerial', self._words)

    def showEvent(self, event):
        if self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantVisible', True)
        super().showEvent(event)

    def hideEvent(self, event):
        if self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantVisible', False)
        super().hideEvent(event)
