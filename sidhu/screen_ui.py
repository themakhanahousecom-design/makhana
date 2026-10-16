"""Desktop-only screen approval/preview flow. There is no unattended capture path."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from .screen import ScreenCaptureService


class ScreenWorkflow:
    def __init__(self, owner, settings, engine, pool, result_callback, log, service=None):
        self.owner, self.settings, self.engine = owner, settings, engine
        self.pool, self.result_callback, self.log = pool, result_callback, log
        self.service = service or ScreenCaptureService()
        self.active = False
        self.indicator = None

    def begin(self):
        if self.active or self.owner.busy or self.owner.exiting:
            self.log('Screen capture unavailable while another task or capture is active.')
            return
        if self.settings.screen_capture_enabled is not True:
            QMessageBox.information(self.owner, 'Screen capture disabled', 'Enable one-shot screen capture in Settings first. No image was captured.')
            return
        self.active = True
        self.owner.busy = True
        self.engine.cancelled.clear()
        self.owner.update_activity()
        self.owner.task_status.setText('Waiting for one-shot capture approval')
        approved = QMessageBox.question(self.owner, 'Capture primary screen once?', 'Capture the primary screen once and preview it locally? Visible applications, including SIDHU, can appear. An indicator will show during capture. Nothing is saved or sent to an AI provider without separate approval.', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if approved != QMessageBox.Yes or self.engine.cancelled.is_set():
            self._finish_local('Screen capture cancelled. No image was taken.')
            return
        self.indicator = QLabel('SIDHU • ONE-SHOT SCREEN CAPTURE APPROVED', None, Qt.Tool | Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.indicator.setStyleSheet('background:#742d35; color:white; padding:14px; font-size:14px;')
        self.indicator.setAttribute(Qt.WA_DeleteOnClose)
        self.indicator.show()
        self.owner.task_status.setText('One-shot screen capture approved; local preview next')
        QTimer.singleShot(250, self._capture)

    def _close_indicator(self):
        if self.indicator is not None:
            self.indicator.close()
            self.indicator = None

    def _finish_local(self, message):
        self._close_indicator()
        self.active = False
        self.owner.busy = False
        self.owner.update_activity()
        self.owner.task_status.setText(message)
        self.log(message)

    def _capture(self):
        if self.owner.exiting or self.engine.cancelled.is_set():
            self._finish_local('Screen capture cancelled before capture.')
            return
        try:
            captured = self.service.capture(confirmed=True)
        except Exception as exc:
            self._finish_local(f'Screen capture unavailable: {exc}')
            return
        self._close_indicator()
        if self.owner.exiting or self.engine.cancelled.is_set():
            self._finish_local('Screen capture discarded after cancellation.')
            return
        self._preview(captured)

    def _preview(self, captured):
        dialog = QDialog(self.owner)
        dialog.setWindowTitle('One-shot screen preview — local only until approved')
        dialog.resize(800, 600)
        layout = QVBoxLayout(dialog)
        label = QLabel()
        image = QPixmap()
        if not image.loadFromData(captured.png, 'PNG'):
            dialog.deleteLater()
            self._finish_local('Captured image could not be previewed; no image was sent.')
            return
        label.setPixmap(image.scaled(740, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        note = QLabel(f'{captured.width}×{captured.height} PNG • held in memory • no automatic save, upload or repeat capture')
        note.setWordWrap(True)
        layout.addWidget(note)
        prompt = QLineEdit('Describe the visible content and visible errors. Do not execute any actions.')
        prompt.setMaxLength(8000)
        layout.addWidget(prompt)
        target = None
        unavailable = ''
        try:
            target = self.engine.ai.vision_target()
            destination = target.base_url
            description = f'Optional image analysis: {destination} / {target.model}. The selected model must support image input.'
        except Exception as exc:
            unavailable = str(exc)
            description = 'AI image analysis unavailable: ' + unavailable
        provider = QLabel(description)
        provider.setTextFormat(Qt.PlainText)
        provider.setWordWrap(True)
        layout.addWidget(provider)
        actions = QHBoxLayout()
        analyze = QPushButton('Approve image analysis…')
        analyze.setEnabled(target is not None)
        discard = QPushButton('Discard image')
        actions.addWidget(analyze)
        actions.addWidget(discard)
        layout.addLayout(actions)
        accepted = []
        def share():
            if not prompt.text().strip():
                provider.setText('Enter a nonempty question before analysis.')
                return
            approval = QMessageBox(dialog)
            approval.setWindowTitle('Send this image to the selected provider?')
            approval.setIcon(QMessageBox.Question)
            approval.setTextFormat(Qt.PlainText)
            approval.setText(f'Send this one image and your question to {destination}, model {target.model}? It may contain private screen contents. The image will not enter saved notes, activity output or text-conversation context.')
            approval.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            approval.setDefaultButton(QMessageBox.No)
            approved = approval.exec()
            approval.deleteLater()
            if approved == QMessageBox.Yes and not self.engine.cancelled.is_set():
                accepted.append(prompt.text())
                dialog.accept()
        analyze.clicked.connect(share)
        discard.clicked.connect(dialog.reject)
        cancel_timer = QTimer(dialog)
        cancel_timer.timeout.connect(lambda: dialog.reject() if self.engine.cancelled.is_set() or self.owner.exiting else None)
        cancel_timer.start(100)
        dialog.exec()
        cancel_timer.stop()
        dialog.deleteLater()
        if not accepted or self.owner.exiting or self.engine.cancelled.is_set():
            self._finish_local('Screen preview discarded locally. No image was sent.')
            return
        self.active = False
        self.owner.task_status.setText('Analyzing one approved image; no further capture')
        question = accepted[0]
        try:
            self.pool.submit(lambda: self.result_callback(self.engine.analyze_screen(captured.png, question, consent=target)))
        except RuntimeError:
            self._finish_local("Image analysis could not start; no image was sent.")
