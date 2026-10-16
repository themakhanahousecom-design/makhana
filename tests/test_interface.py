"""Offscreen checks for actual input levels, animation budgets and safe text display."""
import os
import subprocess
import sys

import pytest


def run_qt(script):
    pytest.importorskip('PySide6')
    result = subprocess.run(
        [sys.executable, '-c', script],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_waveform_uses_measured_audio_and_stops_animation_when_hidden_or_reduced():
    run_qt('''
from PySide6.QtWidgets import QApplication
from sidhu.interface import WaveformWidget, WorkstationBackdrop
app = QApplication([])
wave = WaveformWidget()
wave.resize(250, 210)
wave.set_activity('listening')
wave.show()
app.processEvents()
assert wave._timer.isActive()
for _ in range(3):
    wave._tick()
assert not any(wave._levels), 'Listening does not invent microphone audio.'
wave.set_level(.36)
wave._tick()
assert wave._levels[-1] == .36
wave.set_level(float('nan'))
wave.set_level('not a number')
assert wave._level == .36
wave._sample_time -= 1
wave._tick()
assert wave._levels[-1] == 0, 'Stale microphone data must settle to silence.'
wave.set_activity('muted')
assert not any(wave._levels)
wave.set_activity('listening')
wave.set_level(.4)
wave._tick()
wave.set_activity('speaking')
assert not any(wave._levels), 'Previous microphone levels must not imply speech-output measurement.'
wave.set_performance(True)
assert not wave._timer.isActive()
wave.set_level(.1)
assert wave._levels[-1] == .1, 'Reduced animation still displays real input.'
wave.set_performance(False)
assert wave._timer.isActive()
wave.hide()
assert not wave._timer.isActive()
backdrop = WorkstationBackdrop()
backdrop.resize(800, 600)
backdrop.show()
app.processEvents()
assert not backdrop.grab().isNull()
backdrop.hide()
assert not backdrop._timer.isActive()
''')


def test_response_bubble_handles_plain_text_and_buttons_keep_accessible_labels():
    run_qt('''
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from sidhu.interface import SpeechBubble, NeonButton, BrandMark, THEME
app = QApplication([])
app.setStyleSheet(THEME)
bubble = SpeechBubble()
text = '<b>Actual assistant output</b> ' * 30
bubble.set_message(text, 'RESULT')
assert bubble.message.textFormat() == Qt.PlainText
assert bubble.message.accessibleDescription() == text
assert bubble.message.toolTip() == text
assert len(bubble.message.text()) <= 341
bubble.show()
app.processEvents()
bubble.set_message('Ready', 'ASSISTANT')
bubble.set_performance(True)
assert bubble._opacity.opacity() == 1
bubble.hide()
button = NeonButton('Notes & reminders', 'note')
assert button.accessibleName() == 'Notes & reminders'
assert button.text() == 'Notes && reminders'
clicked = []
button.clicked.connect(lambda: clicked.append(True))
button.click()
assert clicked == [True]
brand = BrandMark()
brand.setFixedSize(405, 105)
brand.show()
app.processEvents()
assert not brand.grab().isNull()
''')
