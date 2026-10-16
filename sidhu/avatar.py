"""Optional real Qt Quick 3D scene, with an explicit lightweight fallback."""
from pathlib import Path
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class AvatarView(QWidget):
    def __init__(self, fallback_factory, enabled=False):
        super().__init__()
        self._activity = 'idle'
        self._words = 0
        self.quick = None
        self.fallback = None
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.fallback_factory = fallback_factory
        if not enabled:
            self._fallback('Lightweight core mode • 3D avatar disabled')
            return
        try:
            from PySide6.QtQuickWidgets import QQuickWidget
            self.quick = QQuickWidget(self)
            from PySide6.QtQuick import QSGRendererInterface
            api = self.quick.quickWindow().rendererInterface().graphicsApi()
            if api == QSGRendererInterface.GraphicsApi.Software:
                self._fallback('3D unavailable: Qt is using software rendering. Lightweight core enabled.')
                return
            self.quick.setResizeMode(QQuickWidget.SizeRootObjectToView)
            self.quick.setMinimumHeight(320)
            context = self.quick.rootContext()
            context.setContextProperty('assistantState', self._activity)
            context.setContextProperty('assistantWordSerial', self._words)
            context.setContextProperty('assistantVisible', False)
            self.layout.addWidget(self.quick)
            self.quick.sceneGraphError.connect(lambda error, message: self._fallback("3D rendering unavailable: " + message))
            self.quick.statusChanged.connect(self._status_changed)
            self.quick.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / 'assets' / 'avatar.qml')))
        except Exception as exc:
            self._fallback(f'3D unavailable: {exc}')

    def _status_changed(self, status):
        from PySide6.QtQuickWidgets import QQuickWidget
        if status == QQuickWidget.Error:
            message = '; '.join(error.toString() for error in self.quick.errors())
            self._fallback('3D scene unavailable: ' + message)

    def _fallback(self, message):
        if self.fallback is not None:
            return
        if self.quick is not None:
            self.quick.hide()
            self.quick.setSource(QUrl())
        self.fallback = self.fallback_factory()
        self.fallback.activity = self._activity
        self.layout.addWidget(self.fallback)
        notice = QLabel(message)
        notice.setWordWrap(True)
        self.layout.addWidget(notice)

    @property
    def activity(self):
        return self._activity

    @activity.setter
    def activity(self, value):
        self._activity = value
        if self.fallback is not None:
            self.fallback.activity = value
            self.fallback.update()
        elif self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantState', value)

    def word(self, location=0, length=0):
        self._words += 1
        if self.quick is not None and self.fallback is None:
            self.quick.rootContext().setContextProperty('assistantWordSerial', self._words)

    def showEvent(self, event):
        if self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantVisible', True)
        super().showEvent(event)

    def hideEvent(self, event):
        if self.quick is not None:
            self.quick.rootContext().setContextProperty('assistantVisible', False)
        super().hideEvent(event)
