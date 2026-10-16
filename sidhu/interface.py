"""Cinematic desktop presentation, independent of the assistant's command engine.

All illustrations here are original vector artwork. The waveform displays measured
audio levels only; its orbit is a decorative status indicator, not microphone data.
"""
from collections import deque
import math
from pathlib import Path
import time

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QIcon, QLinearGradient,
                          QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGraphicsOpacityEffect, QLabel, QPushButton,
                              QSizePolicy, QVBoxLayout, QWidget)


THEME = """
QWidget { color: #e5f5ff; font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 13px; }
QMainWindow, QDialog { background: #07111f; }
QDialog QLabel { background: transparent; }
QLabel { background: transparent; }
QLabel[role='eyebrow'] { color: #71ccf1; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel[role='muted'] { color: #88a9be; font-size: 11px; }
QLabel[role='section'] { color: #e5f8ff; font-size: 14px; font-weight: 600; }
QLabel[role='status'] { color: #73e7ff; font-size: 15px; font-weight: 600; }
QLabel#eyebrow, QLabel#consoleLabel { color: #71ccf1; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel#mutedLabel, QLabel#smallLabel { color: #88a9be; font-size: 11px; }
QLabel#stageEyebrow { color: #84bdcf; font-size: 10px; letter-spacing: 2px; }
QLabel#connectionBadge { color: #9cebdc; font-size: 11px; letter-spacing: 1px; }
QLabel#renderBadge { color: #90d6ef; font-size: 9px; border: 1px solid #25546b; border-radius: 9px; padding: 4px 8px; background: rgba(5, 25, 40, 150); }
QLabel#voiceHeading { color: #e1f7ff; font-size: 20px; font-weight: 600; padding-top: 3px; }
QLabel#taskStatus { color: #90c6df; font-size: 11px; padding: 5px; }
QLabel#transcriptLabel { color: #b5e8fa; font-size: 12px; }
QPushButton { background: rgba(10, 31, 52, 210); color: #dff5ff; border: 1px solid #255b79;
 border-radius: 9px; padding: 9px 13px; min-height: 20px; text-align: left; }
QPushButton:hover { background: rgba(13, 66, 96, 230); border-color: #55d7ff; color: white; }
QPushButton:pressed { background: #15506f; border-color: #a0edff; }
QPushButton:focus { border: 1px solid #a0edff; }
QPushButton:disabled { color: #536f80; border-color: #1c3443; background: #0a1823; }
QPushButton[role='nav'], QPushButton[role='navigation'] { background: transparent; border: none; border-bottom: 1px solid rgba(61, 126, 157, 60);
 border-radius: 0px; padding: 6px 7px; min-height: 18px; }
QPushButton[role='quick'] { padding: 6px 9px; min-height: 18px; }
QPushButton[role='quickCompact'] { padding: 3px 9px; min-height: 18px; font-size: 12px; }
QPushButton[role='nav']:hover, QPushButton[role='navigation']:hover { background: rgba(28, 128, 182, 45); color: white; }
QPushButton[role='primary'] { background: #087aa9; border: 1px solid #5bdcff; color: white; font-weight: 600; text-align: center; }
QPushButton[role='primary']:hover { background: #1399c8; }
QPushButton[role='danger'] { color: #ffc7b8; border-color: #794b4e; }
QPushButton[role='quiet'] { background: rgba(7, 20, 33, 100); color: #9cc8de; border: 1px solid #224559; }
QPushButton#quietButton { background: rgba(7, 20, 33, 100); color: #9cc8de; border: 1px solid #224559; padding: 6px 8px; font-size: 10px; }
QPushButton#settingsButton { background: rgba(11, 35, 54, 180); border: 1px solid #326883; }
QPushButton#stopButton { color: #ffc7b8; border-color: #794b4e; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
 background: rgba(4, 17, 30, 230); border: 1px solid #254d65; border-radius: 7px; padding: 8px;
 color: #e5f5ff; selection-background-color: #087aa9; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4fcaff; }
QTextEdit[role='transcript'] { background: rgba(3, 14, 25, 160); border-color: rgba(41, 99, 128, 100); font-size: 12px; }
QCheckBox { spacing: 8px; padding: 4px 0px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px; border: 1px solid #3c6f89; background: #0b1b29; }
QCheckBox::indicator:checked { background: #26b9e1; border-color: #7de8ff; }
QListWidget, QTableWidget { background: #071726; alternate-background-color: #0a2235; border: 1px solid #254d65; border-radius: 7px; padding: 4px; }
QListWidget::item, QTableWidget::item { padding: 7px; }
QListWidget::item:selected, QTableWidget::item:selected { background: #164e6b; color: white; }
QHeaderView::section { background: #102a3e; color: #b8e8ff; border: none; padding: 7px; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #295773; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTabWidget::pane { border: 1px solid #254d65; border-radius: 7px; }
QTabBar::tab { background: #0c2133; color: #9cc8de; padding: 9px 14px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #dffaff; border-bottom-color: #48d3ff; }
QMenu { background: #0b1f30; border: 1px solid #2b607e; padding: 5px; }
QMenu::item { padding: 7px 20px; }
QMenu::item:selected { background: #14516d; border-radius: 4px; }
QToolTip { background: #10293a; color: #dff7ff; border: 1px solid #43839f; padding: 6px; }
QStatusBar { background: transparent; color: #91b6c8; }
"""


def _gradient(rect, top, bottom):
    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0, QColor(top))
    gradient.setColorAt(1, QColor(bottom))
    return QBrush(gradient)


def _glow(painter, center, radius, color, strength=100):
    glow = QRadialGradient(center, radius)
    shade = QColor(color)
    shade.setAlpha(strength)
    glow.setColorAt(0, shade)
    shade.setAlpha(0)
    glow.setColorAt(1, shade)
    painter.setPen(Qt.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(center, radius, radius)


class AnimatedWidget(QWidget):
    """Visible-only animation. Lightweight mode holds a still illustration."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._reduced = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._phase = (self._phase + 0.016) % (math.pi * 200)
        self.update()

    def set_performance(self, reduced):
        self._reduced = bool(reduced)
        self._sync_timer()
        self.update()

    def _sync_timer(self):
        if self.isVisible() and not self._reduced:
            self._timer.start()
        else:
            self._timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)


class WorkstationBackdrop(AnimatedWidget):
    """Dark studio, amber practical lights, blue monitor glow, and a desk."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('workstationBackdrop')
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        path = Path(__file__).parent / 'assets' / 'workstation.png'
        self._backplate = QPixmap(str(path)) if path.is_file() else QPixmap()
        self._scaled_backplate = QPixmap()
        self._scaled_size = None
        self._scene = QPixmap()
        self._scene_key = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        if not width or not height:
            return
        # Large gradient fields and backplate processing happen once per resize.
        # Animation frames only copy the cached surface and draw 22 dust points.
        ratio = self.devicePixelRatioF()
        key = (width, height, ratio)
        if key != self._scene_key:
            self._scene = QPixmap(round(width * ratio), round(height * ratio))
            self._scene.setDevicePixelRatio(ratio)
            self._scene.fill(QColor('#060d18'))
            scene_painter = QPainter(self._scene)
            scene_painter.setRenderHint(QPainter.Antialiasing)
            self._paint_scene(scene_painter, width, height)
            scene_painter.end()
            self._scene_key = key
        p.drawPixmap(0, 0, self._scene)
        p.save()
        p.scale(width / 1440, height / 960)
        # Restrained atmospheric dust points; never imply sensor data.
        p.setPen(Qt.NoPen)
        for i in range(22):
            x = (i * 173 + 100) % 1440
            y = ((i * 97) % 730) + 35 + math.sin(self._phase + i) * 6
            p.setBrush(QColor(126, 216, 255, 18 + (i % 4) * 6))
            p.drawEllipse(QPointF(x, y), 1.1, 1.1)
        p.restore()

    def _paint_scene(self, p, width, height):
        p.save()
        p.scale(width / 1440, height / 960)
        whole = QRectF(0, 0, 1440, 960)
        p.fillRect(whole, _gradient(whole, '#17232f', '#020a15'))
        if not self._backplate.isNull():
            p.save()
            p.setOpacity(0.44)
            if self._scaled_size != self.size():
                self._scaled_backplate = self._backplate.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self._scaled_size = self.size()
            crop = self._scaled_backplate
            p.resetTransform()
            p.drawPixmap((width - crop.width()) // 2, (height - crop.height()) // 2, crop)
            p.restore()
            p.fillRect(whole, QColor(2, 10, 22, 85))
        else:
            # Original architectural illustration, deliberately low contrast behind controls.
            p.setPen(QPen(QColor(75, 91, 105, 46), 2))
            for x in (14, 325, 700, 1020, 1398):
                p.drawLine(QPointF(x, 0), QPointF(x - 35, 760))
            p.setPen(Qt.NoPen)
            for x, y, w, h in ((30, 60, 300, 220), (1050, 80, 330, 260), (1040, 400, 340, 220)):
                frame = QRectF(x, y, w, h)
                p.setBrush(QColor(3, 10, 18, 170))
                p.drawRoundedRect(frame, 9, 9)
                p.setPen(QPen(QColor(43, 88, 113, 75), 2))
                p.setBrush(QColor(11, 33, 48, 90))
                p.drawRoundedRect(frame.adjusted(9, 9, -9, -9), 4, 4)
                p.setPen(Qt.NoPen)
            # Ceiling downlights and warm wooden ledges.
            for x, y in ((244, 7), (1087, 12), (1377, 40)):
                _glow(p, QPointF(x, y + 30), 160, '#e9a16a', 28)
                p.setBrush(QColor('#c79569'))
                p.drawRoundedRect(QRectF(x - 19, y, 38, 7), 3, 3)
            for x, y, w in ((0, 215, 290), (1090, 365, 350)):
                p.setBrush(QColor(101, 65, 42, 110))
                p.drawRect(QRectF(x, y, w, 10))
                p.setBrush(QColor(228, 170, 100, 120))
                p.drawRect(QRectF(x, y + 8, w, 2))
            # Monitors and soft keyboard light anchor the center to a workstation.
            for x, y, w, h in ((1040, 553, 355, 181), (84, 560, 250, 150)):
                screen = QRectF(x, y, w, h)
                p.setBrush(QColor('#060e18'))
                p.drawRoundedRect(screen, 8, 8)
                p.fillRect(screen.adjusted(8, 8, -8, -10), _gradient(screen, '#132d43', '#071c2c'))
                p.setPen(QPen(QColor(39, 127, 171, 45), 1))
                for index in range(6):
                    p.drawLine(QPointF(x + 20, y + 28 + index * 20), QPointF(x + w - 28 - (index % 3) * 32, y + 28 + index * 20))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#0b1926'))
                p.drawRoundedRect(QRectF(x + w * .44, y + h, w * .12, 53), 3, 3)
        _glow(p, QPointF(740, 460), 560, '#168fce', 37)
        _glow(p, QPointF(260, 345), 300, '#0ca5e0', 15)
        _glow(p, QPointF(1170, 170), 290, '#f3a05a', 19)
        # Perspective tabletop, dark leather mat and a narrow cyan reflection.
        desk = QPainterPath()
        desk.moveTo(0, 831)
        desk.lineTo(1440, 801)
        desk.lineTo(1440, 960)
        desk.lineTo(0, 960)
        desk.closeSubpath()
        p.setBrush(_gradient(QRectF(0, 801, 1440, 159), '#2b2425', '#100f18'))
        p.setPen(QPen(QColor(150, 106, 72, 65), 1))
        p.drawPath(desk)
        _glow(p, QPointF(840, 871), 310, '#1488c6', 24)
        p.setPen(QPen(QColor(64, 177, 223, 25), 1))
        for y in (850, 893, 941):
            p.drawLine(QPointF(0, y), QPointF(1440, y - 26))
        # Deep edge vignette keeps navigation legible against the studio.
        vignette = QRadialGradient(QPointF(720, 450), 870)
        vignette.setColorAt(0, QColor(1, 6, 16, 0))
        vignette.setColorAt(.68, QColor(1, 6, 16, 12))
        vignette.setColorAt(1, QColor(1, 6, 16, 155))
        p.fillRect(whole, vignette)
        p.restore()


class GlassPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('glassPanel')
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)
        self.body.setSpacing(10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        for width, alpha in ((5, 9), (3, 17)):
            p.setPen(QPen(QColor(51, 190, 244, alpha), width))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect, 14, 14)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(17, 54, 78, 208))
        gradient.setColorAt(.45, QColor(7, 26, 44, 208))
        gradient.setColorAt(1, QColor(6, 20, 35, 220))
        p.setBrush(gradient)
        p.setPen(QPen(QColor(77, 191, 239, 100), 1))
        p.drawRoundedRect(rect, 14, 14)
        p.setPen(QPen(QColor(137, 224, 255, 110), 1))
        p.drawLine(QPointF(rect.left() + 17, rect.top()), QPointF(rect.left() + min(80, rect.width() * .4), rect.top()))


def _icon(name, color='#65dfff', size=26):
    """Small original line icons, drawn at high density for sharp HiDPI UI."""
    image = QPixmap(size * 2, size * 2)
    image.setDevicePixelRatio(2)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 24, size / 24)
    p.setPen(QPen(QColor(color), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    if name == 'mic':
        p.drawRoundedRect(QRectF(9, 3, 6, 12), 3, 3)
        p.drawArc(QRectF(6, 7, 12, 12), 180 * 16, 180 * 16)
        p.drawLine(12, 19, 12, 22)
        p.drawLine(8, 22, 16, 22)
    elif name == 'folder':
        path.moveTo(3, 7); path.lineTo(3, 4); path.lineTo(9, 4); path.lineTo(12, 7); path.lineTo(21, 7)
        path.lineTo(19, 20); path.lineTo(3, 20); path.closeSubpath(); p.drawPath(path)
        p.drawLine(3, 9, 20, 9)
    elif name in ('apps', 'windows'):
        for x in (4, 13):
            for y in (4, 13):
                p.drawRoundedRect(QRectF(x, y, 7, 7), 1, 1)
    elif name == 'globe':
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawEllipse(QRectF(8, 3, 8, 18))
        p.drawLine(3, 12, 21, 12); p.drawLine(5, 7, 19, 7); p.drawLine(5, 17, 19, 17)
    elif name == 'chat':
        path.moveTo(8, 20); path.lineTo(3, 22); path.lineTo(4, 16)
        path.cubicTo(-1, 6, 7, 1, 15, 4); path.cubicTo(25, 7, 23, 19, 14, 20); path.closeSubpath(); p.drawPath(path)
        for x in (7, 12, 17):
            p.drawPoint(x, 12)
    elif name in ('tasks', 'note'):
        p.drawRoundedRect(QRectF(4, 3, 16, 19), 2, 2)
        if name == 'tasks':
            p.drawLine(7, 11, 10, 14); p.drawLine(10, 14, 17, 7)
        else:
            for y in (8, 12, 16):
                p.drawLine(8, y, 16 if y != 16 else 13, y)
    elif name == 'settings':
        p.drawEllipse(QRectF(8, 8, 8, 8))
        for i in range(8):
            angle = i * math.pi / 4
            p.drawLine(QPointF(12 + math.cos(angle) * 8, 12 + math.sin(angle) * 8), QPointF(12 + math.cos(angle) * 11, 12 + math.sin(angle) * 11))
        p.drawEllipse(QRectF(4, 4, 16, 16))
    elif name == 'music':
        p.drawLine(10, 17, 10, 5); p.drawLine(10, 5, 20, 3); p.drawLine(20, 3, 20, 15)
        p.drawEllipse(QRectF(3, 16, 7, 5)); p.drawEllipse(QRectF(13, 14, 7, 5))
    elif name == 'camera':
        path.moveTo(3, 7); path.lineTo(8, 7); path.lineTo(10, 4); path.lineTo(15, 4); path.lineTo(17, 7)
        path.lineTo(21, 7); path.lineTo(21, 20); path.lineTo(3, 20); path.closeSubpath(); p.drawPath(path)
        p.drawEllipse(QRectF(8, 9, 8, 8))
    elif name == 'power':
        p.drawArc(QRectF(4, 4, 16, 17), 125 * 16, 290 * 16); p.drawLine(12, 2, 12, 12)
    elif name == 'send':
        path.moveTo(3, 3); path.lineTo(22, 12); path.lineTo(3, 21); path.lineTo(6, 12); path.closeSubpath(); p.drawPath(path)
        p.drawLine(6, 12, 16, 12)
    elif name == 'stop':
        p.drawRoundedRect(QRectF(5, 5, 14, 14), 2, 2)
    elif name == 'clock':
        p.drawEllipse(QRectF(3, 3, 18, 18)); p.drawLine(12, 7, 12, 12); p.drawLine(12, 12, 16, 14)
    else:
        path.moveTo(12, 2); path.lineTo(15, 9); path.lineTo(22, 12); path.lineTo(15, 15)
        path.lineTo(12, 22); path.lineTo(9, 15); path.lineTo(2, 12); path.lineTo(9, 9); path.closeSubpath(); p.drawPath(path)
    p.end()
    return QIcon(image)


class NeonButton(QPushButton):
    def __init__(self, text, icon='spark', parent=None):
        super().__init__(text.replace('&', '&&'), parent)
        self.setIcon(_icon(icon))
        from PySide6.QtCore import QSize
        self.setIconSize(QSize(24, 24))
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(text)
        self.setMinimumHeight(40)


class BrandMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._compact = False
        self.setMinimumHeight(105)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName('SIDHU AI — Your personal AI assistant')

    def set_compact(self, compact):
        self._compact = bool(compact)
        self.setMinimumHeight(80 if compact else 105)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        scale = min(width / 430, self.height() / 105, 1.28)
        p.scale(scale, scale)
        crown = QPainterPath()
        crown.moveTo(188, 2); crown.lineTo(196, 17); crown.lineTo(208, 2)
        crown.lineTo(220, 17); crown.lineTo(228, 2); crown.lineTo(224, 26)
        crown.lineTo(192, 26); crown.closeSubpath()
        for pen_width, alpha in ((10, 9), (6, 22), (2, 240)):
            p.setPen(QPen(QColor(109, 220, 255, alpha), pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush); p.drawPath(crown)
        p.setPen(QPen(QColor('#75dfff'), 1.5)); p.drawLine(192, 30, 224, 30)
        font = QFont('Segoe UI', 43, QFont.Bold)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        p.setFont(font)
        path = QPainterPath()
        path.addText(QPointF(1, 81), font, 'SIDHU AI')
        rect = path.boundingRect()
        # Fit the wordmark to the actual allocated width, including narrow layouts.
        p.save()
        factor = 417 / max(1.0, rect.width())
        p.scale(factor, 1)
        for pen_width, alpha in ((16, 4), (10, 10), (5, 20)):
            p.setPen(QPen(QColor(12, 163, 255, alpha), pen_width))
            p.setBrush(Qt.NoBrush); p.drawPath(path)
        title_gradient = QLinearGradient(0, 37, 0, 83)
        title_gradient.setColorAt(0, QColor('#ffffff'))
        title_gradient.setColorAt(.48, QColor('#bcefff'))
        title_gradient.setColorAt(1, QColor('#21bded'))
        p.setPen(QPen(QColor('#93e7ff'), .7)); p.setBrush(title_gradient); p.drawPath(path)
        p.restore()
        p.setFont(QFont('Segoe UI', 10, QFont.Medium))
        p.setPen(QColor('#c8e7f6'))
        p.drawText(QRectF(2, 86, 417, 19), Qt.AlignHCenter | Qt.AlignVCenter, 'YOUR PERSONAL AI ASSISTANT')


class SpeechBubble(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(115)
        self.setMaximumHeight(195)
        self.setAttribute(Qt.WA_TranslucentBackground)
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 16, 22, 28)
        body.setSpacing(7)
        self.caption = QLabel('ASSISTANT')
        self.caption.setProperty('role', 'eyebrow')
        self.message = QLabel('Ready when you are.')
        self.message.setWordWrap(True)
        self.message.setStyleSheet('font-size: 20px; font-weight: 600; color: #e5f8ff;')
        self.message.setTextFormat(Qt.PlainText)
        self.message.setMaximumHeight(118)
        self.caption.setTextFormat(Qt.PlainText)
        body.addWidget(self.caption)
        body.addWidget(self.message)
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1)
        self.setGraphicsEffect(self._opacity)
        self._animation = QPropertyAnimation(self._opacity, b'opacity', self)
        self._animation.setDuration(320)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        self._reduced = False

    def set_performance(self, reduced):
        self._reduced = bool(reduced)
        if reduced:
            self._animation.stop()
            self._opacity.setOpacity(1)

    def set_message(self, text, caption='ASSISTANT'):
        # The full response remains available to assistive technologies and a tooltip.
        text = str(text)
        self.message.setText(text[:340] + ('…' if len(text) > 340 else ''))
        self.message.setToolTip(text)
        self.message.setAccessibleDescription(text)
        self.caption.setText(str(caption))
        self._animation.stop()
        if self.isVisible() and not self._reduced:
            self._animation.setStartValue(.4)
            self._animation.setEndValue(1.0)
            self._animation.start()
        else:
            self._opacity.setOpacity(1)

    def hideEvent(self, event):
        self._animation.stop()
        self._opacity.setOpacity(1)
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -19)
        path = QPainterPath()
        path.addRoundedRect(rect, 20, 20)
        tail = QPainterPath()
        tail.moveTo(rect.right() - 55, rect.bottom() - 1)
        tail.lineTo(rect.right() - 18, rect.bottom() + 17)
        tail.lineTo(rect.right() - 26, rect.bottom() - 4)
        tail.closeSubpath()
        path = path.united(tail)
        p.setBrush(_gradient(rect, '#0a3255', '#071c35'))
        for width, alpha in ((7, 12), (3, 29), (1.3, 220)):
            p.setPen(QPen(QColor(70, 201, 255, alpha), width))
            p.drawPath(path)


class WaveformWidget(AnimatedWidget):
    """A status orbit with a waveform derived exclusively from measured RMS.

    In the absence of fresh audio, the line settles to zero instead of displaying
    invented listening levels. Calling set_level is safe while animation is reduced.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(185)
        self._levels = deque([0.0] * 66, maxlen=66)
        self._level = 0.0
        self._sample_time = 0.0
        self._activity = 'idle'
        self.setAccessibleName('Microphone audio level')
        self.setAccessibleDescription('Flat line until measured microphone audio is available.')

    def set_level(self, level):
        try:
            level = float(level)
        except (TypeError, ValueError):
            return
        if not math.isfinite(level):
            return
        self._level = max(0.0, min(1.0, level))
        self._sample_time = time.monotonic()
        if self._reduced or not self._timer.isActive():
            self._levels.append(self._level)
            self.update()

    def set_activity(self, activity):
        self._activity = str(activity)
        self.setAccessibleDescription(f'{self._activity}. Waveform shows measured microphone levels only.')
        if self._activity != 'listening':
            self._level = 0.0
            self._levels = deque([0.0] * 66, maxlen=66)
        self.update()

    def _tick(self):
        if time.monotonic() - self._sample_time > .25:
            self._level = 0.0
        self._levels.append(self._level)
        super()._tick()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        center = QPointF(width / 2, height * .39)
        radius = min(48, width * .21, height * .245)
        active = self._activity not in ('idle', 'muted', 'stopped', 'error')
        pulse = 1 + .035 * math.sin(self._phase * 2) if active else 1
        _glow(p, center, radius * 1.9, '#009dff', 55 if active else 22)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(51, 145, 202, 40), 1))
        p.drawEllipse(center, radius * 1.45, radius * 1.45)
        p.drawEllipse(center, radius * 1.25, radius * 1.25)
        p.setPen(QPen(QColor(73, 193, 253, 90 if active else 42), 1))
        p.drawEllipse(center, radius * pulse, radius * pulse)
        p.setPen(QPen(QColor(84, 213, 255, 180 if active else 65), 1.6))
        orbit = QRectF(center.x() - radius * 1.22, center.y() - radius * 1.22, radius * 2.44, radius * 2.44)
        p.drawArc(orbit, int(self._phase * 15 * 16) if active else 0, 70 * 16)
        p.drawArc(orbit, (int(self._phase * 15 * 16) if active else 0) + 180 * 16, 70 * 16)
        icon = _icon('mic', '#8beeff' if active else '#517e96', 48)
        icon.paint(p, int(center.x() - 24), int(center.y() - 24), 48, 48)
        baseline = height * .83
        left, right = 9.0, width - 9.0
        p.setPen(QPen(QColor(57, 153, 199, 42), 1))
        p.drawLine(QPointF(left, baseline), QPointF(right, baseline))
        step = (right - left) / (len(self._levels) - 1)
        for index, value in enumerate(self._levels):
            # Square root compression makes quiet real signals visible without
            # introducing random, periodic, or fabricated audio amplitudes.
            amplitude = math.sqrt(value) * min(31, height * .145)
            x = left + index * step
            p.setPen(QPen(QColor(37, 189, 255, 25), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, baseline - amplitude), QPointF(x, baseline + amplitude))
            p.setPen(QPen(QColor(74, 224, 255, 225 if value else 90), 1.8, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x, baseline - amplitude), QPointF(x, baseline + amplitude))
