import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import sys
from .config import Settings, data_dir
from .core import Engine
from .memory import Memory


def main():
    parser = argparse.ArgumentParser(description="SIDHU AI Windows assistant")
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--supervise", action="store_true", help="Restart the desktop after abnormal exit, with a bounded retry policy")
    parser.add_argument("--supervised-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--recovering", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--command", help="Run a typed command without starting the desktop UI")
    args = parser.parse_args()
    if args.supervise and (args.command is not None or args.supervised_child or args.recovering):
        parser.error("--supervise cannot be combined with a command or internal child flags")
    if args.recovering and not args.supervised_child:
        parser.error("--recovering is an internal supervised-child option")
    folder = data_dir()
    if args.supervise:
        from .supervisor import Supervisor
        return Supervisor(folder).run(background=args.background)
    settings = Settings.load(folder / "settings.json")
    engine = Engine(settings, Memory(folder / "memory.sqlite3"))
    if args.command is not None:
        result = engine.execute(args.command)
        print(json.dumps(asdict(result), ensure_ascii=False))
        return 0 if result.ok else 1
    return desktop(settings, engine, folder, args.background, recovering=args.recovering)


def desktop(settings, engine, folder, background, recovering=False):
    from PySide6.QtCore import QObject, Signal, QTimer, Qt, QLockFile
    from PySide6.QtGui import QAction, QColor, QPainter, QPen, QTextCursor
    from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QSystemTrayIcon, QMenu, QStyle, QDialog, QFormLayout, QCheckBox, QSpinBox, QDialogButtonBox, QMessageBox, QScrollArea, QListWidget, QListWidgetItem, QInputDialog, QFileDialog, QTableWidget, QTableWidgetItem, QTabWidget)
    from .voice import VoiceService, Speaker
    from .windows import set_autostart

    class Events(QObject):
        command = Signal(str)
        voice_command = Signal(int, str)
        status = Signal(str)
        partial = Signal(str)
        result = Signal(object)
        voice_state = Signal(str)
        speech_state = Signal(str)
        speech_status = Signal(str)
        progress = Signal(str)
        speech_word = Signal(int, int)

    class CoreVisual(QWidget):
        def __init__(self):
            super().__init__()
            self.setMinimumHeight(170)
            self.phase = 0
            self.activity = "idle"
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.tick)
            self.timer.start(50)

        def tick(self):
            if self.isVisible() and not settings.lightweight:
                self.phase = (self.phase + 2) % 360
                self.update()

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            cx, cy = self.width() // 2, self.height() // 2
            p.translate(cx, cy)
            for r in (55, 68, 78):
                p.setPen(QPen(QColor("#39dfc4"), 2))
                p.drawArc(-r, -r, r*2, r*2, int(self.phase * 16 + r), 260*16)
            p.setPen(QColor("#f0d09a"))
            p.drawText(-48, -8, 96, 24, Qt.AlignCenter, "SIDHU AI")
            p.drawText(-65, 14, 130, 24, Qt.AlignCenter, self.activity.upper())

    class PlainLog(QTextEdit):
        def append(self, text):
            self.moveCursor(QTextCursor.End)
            self.insertPlainText(str(text) + "\n")

    class Window(QMainWindow):
        def __init__(self):
            super().__init__()
            self.events = Events()
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sidhu-task")
            self.busy = False
            self.exiting = False
            from .screen_ui import ScreenWorkflow
            self.screen_flow = ScreenWorkflow(self, settings, engine, self.pool, self.events.result.emit, lambda message: self.log.append(message))
            self.listener_generation = 0
            self.voice = VoiceService(settings, lambda text: self.events.voice_command.emit(0, text), self.events.status.emit, self.events.partial.emit, self.events.voice_state.emit)
            self.speaker = Speaker(settings, self.voice.speaking, self.events.speech_status.emit, self.events.speech_state.emit, on_word=self.events.speech_word.emit)
            self.setWindowTitle("SIDHU AI • Desktop Assistant")
            self.resize(860, 760)
            base = QWidget()
            self.setCentralWidget(base)
            layout = QVBoxLayout(base)
            title = QLabel("SIDHU / AI     ·     PERSONAL COMMAND CENTER")
            title.setStyleSheet("font-size:23px; color:#f0d09a; padding:15px")
            layout.addWidget(title)
            from .avatar import AvatarView
            self.visual = AvatarView(CoreVisual, enabled=settings.avatar_enabled and not settings.lightweight)
            self.events.speech_word.connect(self.visual.word)
            layout.addWidget(self.visual)
            self.status = QLabel("Microphone muted. Enable listening when ready.")
            self.partial = QLabel("")
            layout.addWidget(self.status)
            self.speech_status = QLabel("Speech idle")
            layout.addWidget(self.speech_status)
            self.task_status = QLabel("Task engine idle")
            layout.addWidget(self.task_status)
            layout.addWidget(self.partial)
            self.stats = QLabel()
            layout.addWidget(self.stats)
            self.log = PlainLog()
            self.log.setReadOnly(True)
            self.log.setAcceptRichText(False)
            layout.addWidget(self.log)
            self.entry = QLineEdit()
            self.entry.setPlaceholderText("Try diagnostics, open Chrome, latest PDF, help…")
            self.entry.returnPressed.connect(self.submit)
            layout.addWidget(self.entry)
            row = QHBoxLayout()
            for index, (label, handler) in enumerate((("Run command", self.submit), ("Enable / mute microphone", self.toggle_voice), ("Stop speech / cancel task", self.cancel), ("Settings", self.configure), ("Workflows", self.configure_workflows), ("Memory", self.manage_memory), ("Productivity", self.manage_productivity), ("Activity", self.manage_activity), ("Screen", self.screen_flow.begin), ("Capabilities", self.capabilities))):
                if index in (3, 6, 9):
                    layout.addLayout(row)
                    row = QHBoxLayout()
                button = QPushButton(label)
                button.clicked.connect(handler)
                row.addWidget(button)
            layout.addLayout(row)
            self.events.command.connect(self.dispatch)
            self.events.voice_command.connect(self.dispatch_voice)
            self.events.status.connect(self.status.setText)
            self.events.speech_status.connect(self.speech_status.setText)
            self.events.voice_state.connect(lambda state: self.update_activity())
            self.events.speech_state.connect(lambda state: self.update_activity())
            self.events.partial.connect(self.partial.setText)
            self.events.result.connect(self.finished)
            self.events.progress.connect(self.task_status.setText)
            self.events.progress.connect(self.log.append)
            engine.on_progress = self.events.progress.emit
            self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.SP_ComputerIcon), self)
            menu = QMenu()
            for label, handler in (("Open dashboard", self.showNormal), ("Enable / mute microphone", self.toggle_voice), ("Exit SIDHU AI", self.quit)):
                action = QAction(label, self)
                action.triggered.connect(handler)
                menu.addAction(action)
            self.tray.setContextMenu(menu)
            self.tray.setToolTip("SIDHU AI — local assistant")
            self.tray.activated.connect(lambda reason: self.showNormal() if reason == QSystemTrayIcon.Trigger else None)
            self.tray.show()
            self.timer = QTimer(self)
            from .productivity import ReminderScheduler
            self.scheduler = ReminderScheduler(engine.productivity, self.notify_reminder, self.log.append)
            self.reminder_timer = QTimer(self)
            self.reminder_timer.timeout.connect(self.scheduler.tick)
            self.reminder_timer.start(1000)
            self.timer.timeout.connect(self.refresh_stats)
            self.timer.start(2000)
            self.refresh_stats()
            self.log.append("SIDHU AI MVP. Type help for commands. Original procedural 3D avatar is optional in Settings. Word-driven mouth animation is not phoneme-level lip sync. Listening is paused during TTS to avoid self-triggering. Stop speech / cancel task interrupts audio; spoken barge-in is not yet supported.")
            if background and not recovering:
                self._start_voice()
            if recovering:
                self.status.setText("Recovered after an abnormal exit. Microphone muted; enable listening when ready.")
                self.log.append("Watchdog recovery: microphone remains muted. Review supervisor status for saved restart observations.")
            if not background or not QSystemTrayIcon.isSystemTrayAvailable():
                self.show()

        def notify_reminder(self, reminder_id, body, due):
            self.log.append(f"Reminder {reminder_id}: {body}")
            if QSystemTrayIcon.isSystemTrayAvailable() and QSystemTrayIcon.supportsMessages():
                self.tray.showMessage("SIDHU reminder", body, QSystemTrayIcon.Information, 10000)
                self.log.append(f"Reminder {reminder_id} dispatched to tray; Windows may suppress notifications.")
            else:
                self.showNormal()
                self.log.append(f"Reminder {reminder_id} displayed in the dashboard; tray notifications unavailable.")

        def update_activity(self):
            self.visual.activity = "speaking" if self.voice.speaking.is_set() else "processing" if self.busy else self.voice.state
            self.visual.update()

        def refresh_stats(self):
            import psutil
            vm = psutil.virtual_memory()
            self.stats.setText(f"CPU {psutil.cpu_percent()}%  ·  RAM {vm.percent}% / {vm.total / 1024**3:.1f} GiB  ·  queued tasks: {'1' if self.busy else '0'}")

        def dispatch_voice(self, generation, text):
            if generation != self.listener_generation or self.exiting or self.voice.stop_event.is_set() or self.voice.state not in {"listening"}:
                return
            self.dispatch(text)

        def submit(self):
            text = self.entry.text()
            self.entry.clear()
            self.dispatch(text)

        def dispatch(self, text):
            if text.strip().casefold() in {"capture screen", "analyze screen"}:
                self.screen_flow.begin()
                return
            if text.casefold() in ("cancel", "stop", "ruk jao"):
                self.cancel()
                return
            if self.busy:
                self.log.append("Busy: cancel or wait for the current task.")
                return
            self.busy = True
            engine.cancelled.clear()
            self.update_activity()
            self.log.append("You: " + text)
            self.task_status.setText("Processing command…")
            self.pool.submit(lambda: self.events.result.emit(engine.execute(text, reset_cancellation=False)))

        def finished(self, result):
            self.busy = False
            self.update_activity()
            self.log.append(f"[{result.agent}] {'OK' if result.ok else 'UNAVAILABLE / ERROR'}: {result.message}")
            outcome = "Task completed" if result.ok else "Task failed or unavailable"
            self.task_status.setText(f"{outcome} • {result.elapsed_ms:.2f} ms (execution only)")
            if result.history_warning:
                self.log.append(result.history_warning)
            # Keep microphone errors/loading/mute status separate from task outcomes.
            if result.ok and not engine.cancelled.is_set():
                self.speaker.say(result.message)

        def cancel(self):
            engine.cancelled.set()
            self.speaker.stop()
            self.log.append("Speech stopped and task cancellation requested. Network requests finish within their timeout; dispatched app launches cannot be undone.")

        def _start_voice(self):
            self.listener_generation += 1
            generation = self.listener_generation
            self.voice.on_command = lambda text: self.events.voice_command.emit(generation, text)
            self.voice.start()

        def _stop_voice(self):
            self.listener_generation += 1
            self.voice.stop()
            self.partial.clear()

        def toggle_voice(self):
            if self.voice.thread and self.voice.thread.is_alive():
                self._stop_voice()
            else:
                self._start_voice()

        def configure(self):
            dialog = QDialog(self)
            dialog.setWindowTitle("SIDHU settings — local storage")
            dialog.resize(760, 700)
            outer = QVBoxLayout(dialog)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            content = QWidget()
            form = QFormLayout(content)
            scroll.setWidget(content)
            outer.addWidget(scroll)
            edits = {}
            for name, label in (("model_path", "Extracted Vosk model folder"), ("voice_id", "Installed TTS voice ID (blank = system default)"), ("ai_base_url", "OpenAI-compatible base URL"), ("ai_model", "Model name"), ("ai_key_env", "API key environment variable name"), ("browser_executable", "Chromium executable (blank = Playwright installed browser)")):
                edit = QLineEdit(getattr(settings, name))
                edits[name] = edit
                form.addRow(label, edit)
            domains = QLineEdit(",".join(settings.browser_domains))
            form.addRow("Browser approved hostnames (comma separated)", domains)
            folders = QLineEdit(";".join(settings.approved_folders))
            form.addRow("Approved search folders (; separated)", folders)
            apps = QLineEdit(",".join(settings.allowed_apps))
            form.addRow("Allowed apps (chrome,edge,explorer,notepad)", apps)
            mic = QSpinBox()
            mic.setRange(-1, 100)
            mic.setValue(-1 if settings.microphone is None else settings.microphone)
            form.addRow("Microphone device index (-1 default)", mic)
            devices = QPushButton("List microphone devices")
            def list_devices():
                try:
                    import sounddevice
                    QMessageBox.information(dialog, "Audio devices", str(sounddevice.query_devices()))
                except Exception as exc:
                    QMessageBox.warning(dialog, "Audio devices", str(exc))
            devices.clicked.connect(list_devices)
            form.addRow(devices)
            checks = {}
            for name, label in (("memory_enabled", "Enable explicit note memory"), ("productivity_enabled", "Enable local tasks and reminders"), ("history_enabled", "Store activity metadata (no command text or output)"), ("window_control_enabled", "Enable native window controls (exact titles; Windows only)"), ("screen_capture_enabled", "Enable one-shot screen capture (approval for every image)"), ("ai_context_enabled", "Keep temporary AI conversation context (sent to selected provider)"), ("speech_enabled", "Speak command results"), ("autostart", "Start in tray at Windows sign-in"), ("lightweight", "Reduce animations"), ("avatar_enabled", "Enable original procedural 3D avatar (restart required; GPU needed)"), ("browser_enabled", "Enable read-only browser inspection")):
                check = QCheckBox(label)
                check.setChecked(getattr(settings, name))
                checks[name] = check
                form.addRow(check)
            follow = QSpinBox()
            follow.setRange(3, 60)
            follow.setValue(settings.followup_seconds)
            form.addRow("Follow-up window (seconds)", follow)
            speed = QSpinBox()
            speed.setRange(80, 300)
            speed.setValue(settings.speech_rate)
            form.addRow("Speech rate", speed)
            clear = QPushButton("Delete all saved notes…")
            def clear_memory():
                if QMessageBox.question(dialog, "Delete memory", "Permanently delete all saved notes?") == QMessageBox.Yes:
                    engine.memory.clear()
            clear.clicked.connect(clear_memory)
            form.addRow(clear)
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            outer.addWidget(buttons)
            if dialog.exec() == QDialog.Accepted:
                desired = checks["autostart"].isChecked()
                if desired or desired != settings.autostart:
                    try:
                        set_autostart(desired)
                    except Exception as exc:
                        QMessageBox.warning(self, "Startup failed", str(exc))
                        return
                self._stop_voice()
                engine.ai.reconfigure(base_url=edits["ai_base_url"].text().strip(), model=edits["ai_model"].text().strip(), key_env=edits["ai_key_env"].text().strip(), keep_context=checks["ai_context_enabled"].isChecked())
                if not checks["speech_enabled"].isChecked():
                    self.speaker.stop()
                for name, edit in edits.items():
                    if name not in {"ai_base_url", "ai_model", "ai_key_env"}:
                        setattr(settings, name, edit.text().strip())
                for name, check in checks.items():
                    if name != "ai_context_enabled":
                        setattr(settings, name, check.isChecked())
                settings.browser_domains = [domain.strip().casefold() for domain in domains.text().split(",") if domain.strip()]
                settings.microphone = None if mic.value() == -1 else mic.value()
                settings.approved_folders = [p.strip() for p in folders.text().split(";") if p.strip()]
                settings.allowed_apps = [p.strip() for p in apps.text().split(",") if p.strip() in {"chrome", "edge", "explorer", "notepad"}]
                settings.followup_seconds = follow.value()
                settings.speech_rate = speed.value()
                settings.save(folder / "settings.json")
                self.status.setText("Settings saved. Microphone muted; enable to use the new configuration.")

        def manage_activity(self):
            if not settings.history_enabled:
                QMessageBox.information(self, "Activity disabled", "Enable activity metadata in Settings. Command text, prompts, paths and tool output are never stored in this history.")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Activity — metadata only")
            dialog.resize(850, 500)
            layout = QVBoxLayout(dialog)
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(["Time (UTC)", "Operation", "Agent", "Result", "Execution ms"])
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            layout.addWidget(table)
            notice = QLabel("Latest 200 of up to 500 records. Execution time excludes recognition, speech and history storage.")
            notice.setWordWrap(True)
            layout.addWidget(notice)
            def refresh():
                try:
                    entries = engine.activity.list()
                    table.setRowCount(len(entries))
                    for row, (at, operation, agent, ok, elapsed) in enumerate(entries):
                        for column, value in enumerate((at, operation, agent, "OK" if ok else "failed / unavailable", f"{elapsed:.2f}")):
                            table.setItem(row, column, QTableWidgetItem(value))
                    table.resizeColumnsToContents()
                except Exception as exc:
                    notice.setText(str(exc))
            def clear():
                if QMessageBox.question(dialog, "Clear activity", "Permanently delete all saved activity metadata?") == QMessageBox.Yes:
                    try:
                        engine.activity.clear()
                        refresh()
                    except Exception as exc:
                        notice.setText(str(exc))
            row = QHBoxLayout()
            for label, handler in (("Refresh", refresh), ("Delete all…", clear), ("Close", dialog.accept)):
                button = QPushButton(label)
                button.clicked.connect(handler)
                row.addWidget(button)
            layout.addLayout(row)
            refresh()
            dialog.exec()

        def manage_productivity(self):
            from .productivity import format_time
            if not settings.productivity_enabled:
                QMessageBox.information(self, "Productivity disabled", "Enable local tasks and reminders in Settings. Nothing is stored while disabled.")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Local tasks and reminders")
            dialog.resize(780, 540)
            layout = QVBoxLayout(dialog)
            tabs = QTabWidget()
            tasks = QTableWidget(0, 3)
            tasks.setHorizontalHeaderLabels(["ID", "Task", "State"])
            reminders = QTableWidget(0, 4)
            reminders.setHorizontalHeaderLabels(["ID", "Reminder", "Due (local time)", "State"])
            for table in (tasks, reminders):
                table.setEditTriggers(QTableWidget.NoEditTriggers)
                table.setSelectionBehavior(QTableWidget.SelectRows)
                table.horizontalHeader().setStretchLastSection(True)
            tabs.addTab(tasks, "Tasks")
            tabs.addTab(reminders, "Reminders")
            layout.addWidget(tabs)
            notice = QLabel("Shows up to 200 recent entries. Reminders require SIDHU running; dispatch does not confirm receipt.")
            notice.setWordWrap(True)
            layout.addWidget(notice)
            def refresh():
                task_rows = engine.productivity.tasks()
                tasks.setRowCount(len(task_rows))
                for row, (task_id, body, done) in enumerate(task_rows):
                    for column, value in enumerate((str(task_id), body, "done" if done else "open")):
                        tasks.setItem(row, column, QTableWidgetItem(value))
                reminder_rows = engine.productivity.reminders()
                reminders.setRowCount(len(reminder_rows))
                for row, (reminder_id, body, due, state) in enumerate(reminder_rows):
                    for column, value in enumerate((str(reminder_id), body, format_time(due), state)):
                        reminders.setItem(row, column, QTableWidgetItem(value))
                tasks.resizeColumnToContents(0)
                reminders.resizeColumnToContents(0)
            def run(action):
                try:
                    action()
                    refresh()
                except Exception as exc:
                    notice.setText(str(exc))
            def add_task():
                text, accepted = QInputDialog.getMultiLineText(dialog, "Add task", "Task text")
                if accepted:
                    run(lambda: engine.productivity.add_task(text))
            def mark_task(done):
                row = tasks.currentRow()
                if row < 0:
                    notice.setText("Select a task.")
                    return
                run(lambda: engine.productivity.set_done(int(tasks.item(row, 0).text()), done))
            def add_reminder():
                text, accepted = QInputDialog.getMultiLineText(dialog, "Add reminder", "Reminder text")
                if not accepted:
                    return
                minutes, accepted = QInputDialog.getInt(dialog, "Delay", "Minutes from now", 10, 1, 525600)
                if accepted:
                    run(lambda: engine.productivity.add_reminder(minutes, text))
            def cancel_reminder():
                row = reminders.currentRow()
                if row < 0:
                    notice.setText("Select a pending reminder.")
                    return
                run(lambda: engine.productivity.cancel_reminder(int(reminders.item(row, 0).text())))
            def clear_all():
                if QMessageBox.question(dialog, "Delete productivity data", "Permanently delete all local tasks and reminders?") == QMessageBox.Yes:
                    run(engine.productivity.clear)
            row = QHBoxLayout()
            for label, handler in (("Add task", add_task), ("Done", lambda: mark_task(True)), ("Reopen", lambda: mark_task(False)), ("Add reminder", add_reminder), ("Cancel reminder", cancel_reminder), ("Delete all…", clear_all), ("Refresh", refresh), ("Close", dialog.accept)):
                button = QPushButton(label)
                button.clicked.connect(handler)
                row.addWidget(button)
            layout.addLayout(row)
            refresh()
            dialog.exec()

        def manage_memory(self):
            if not settings.memory_enabled:
                QMessageBox.information(self, "Memory disabled", "Enable explicit note memory in Settings to view, edit or export notes. Existing notes are retained until deleted.")
                return
            dialog = QDialog(self)
            dialog.setWindowTitle("Local note memory")
            dialog.resize(720, 520)
            layout = QVBoxLayout(dialog)
            query = QLineEdit()
            query.setPlaceholderText("Search saved notes…")
            layout.addWidget(query)
            notes = QListWidget()
            layout.addWidget(notes)
            notice = QLabel("Only explicitly saved notes are stored. Avoid credentials and sensitive data.")
            layout.addWidget(notice)
            def refresh():
                notes.clear()
                try:
                    for note_id, body in engine.memory.search(query.text()):
                        item = QListWidgetItem(f"{note_id}: {body[:200]}")
                        item.setData(Qt.UserRole, (note_id, body))
                        notes.addItem(item)
                except Exception as exc:
                    notice.setText(str(exc))
            query.textChanged.connect(refresh)
            def edit_note():
                item = notes.currentItem()
                if item is None:
                    notice.setText("Select a note to edit.")
                    return
                note_id, body = item.data(Qt.UserRole)
                text, accepted = QInputDialog.getMultiLineText(dialog, "Edit note", "Note text", body)
                if accepted:
                    try:
                        engine.memory.update(note_id, text)
                        refresh()
                    except Exception as exc:
                        notice.setText(str(exc))
            def delete_note():
                item = notes.currentItem()
                if item is None:
                    notice.setText("Select a note to delete.")
                    return
                note_id, _ = item.data(Qt.UserRole)
                if QMessageBox.question(dialog, "Delete note", f"Permanently delete note {note_id}?") == QMessageBox.Yes:
                    try:
                        engine.memory.delete(note_id)
                        refresh()
                    except Exception as exc:
                        notice.setText(str(exc))
            def export_notes():
                filename, _ = QFileDialog.getSaveFileName(dialog, "Export notes to a NEW file", "sidhu-notes.json", "JSON (*.json)")
                if not filename:
                    return
                try:
                    contents = [{"id": note_id, "text": body} for note_id, body in engine.memory.list()]
                    from pathlib import Path
                    with Path(filename).open("x", encoding="utf-8") as stream:
                        json.dump(contents, stream, ensure_ascii=False, indent=2)
                    notice.setText("Notes exported. The export is a separate unencrypted file.")
                except Exception as exc:
                    notice.setText(f"Export failed (existing files are never overwritten): {exc}")
            row = QHBoxLayout()
            for label, handler in (("Edit selected", edit_note), ("Delete selected…", delete_note), ("Export all…", export_notes), ("Close", dialog.accept)):
                button = QPushButton(label)
                button.clicked.connect(handler)
                row.addWidget(button)
            layout.addLayout(row)
            refresh()
            dialog.exec()

        def configure_workflows(self):
            from .workflows import validate_workflows
            dialog = QDialog(self)
            dialog.setWindowTitle("Saved workflows — supported commands only")
            dialog.resize(700, 500)
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel('Edit named command sequences as JSON. Example: {"work setup": ["open Chrome", "diagnostics"]}'))
            editor = QTextEdit()
            editor.setAcceptRichText(False)
            editor.setPlainText(json.dumps(settings.workflows, ensure_ascii=False, indent=2))
            layout.addWidget(editor)
            error = QLabel("")
            layout.addWidget(error)
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            def save():
                try:
                    workflows = validate_workflows(json.loads(editor.toPlainText()))
                    previous = settings.workflows
                    settings.workflows = workflows
                    try:
                        settings.save(folder / "settings.json")
                    except Exception:
                        settings.workflows = previous
                        raise
                except Exception as exc:
                    error.setText(str(exc))
                    return
                dialog.accept()
            buttons.accepted.connect(save)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            dialog.exec()

        def capabilities(self):
            QMessageBox.information(self, "Actual capability status", "IMPLEMENTED: deterministic command routing, diagnostics, approved-folder search, opt-in notes, settings, bounded saved workflows, text previews/content search, recent files, duplicate detection, note management, local tasks and reminders, opt-in activity metadata, execution timing, hardware/process reports, local document/CSV tools, optional transient AI context, optional bounded watchdog, native window controls, opt-in one-shot screen preview and optional vision input.\nWINDOWS TEST REQUIRED: app launch, volume, tray, autostart, packaged app, watchdog restarts, native window actions, physical screen capture, SAPI speech.\nREQUIRES CONFIGURATION: Vosk language model and microphone; AI text/vision provider/model; installed multilingual TTS voices; optional Playwright/Chromium and approved hostnames for inspection.\nPARTIAL: local wake phrase via full speech recognition, cancellation, audio recovery.\nNOT IMPLEMENTED: realistic licensed character/phoneme lip sync, voice barge-in, browser form/click workflows, continuous/automatic screen observation, coding execution, calendar integrations, advanced multi-agent planning. No licensed voice or likeness is bundled.")

        def closeEvent(self, event):
            if self.exiting:
                event.accept()
            elif QSystemTrayIcon.isSystemTrayAvailable():
                self.hide()
                event.ignore()
            else:
                self.quit()
                event.accept()

        def quit(self):
            self.exiting = True
            self.reminder_timer.stop()
            self.screen_flow._close_indicator()
            self._stop_voice()
            self.speaker.close()
            engine.ai.clear()
            engine.cancelled.set()
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.tray.hide()
            QApplication.quit()

    app = QApplication(sys.argv)
    instance_lock = QLockFile(str(folder / "desktop.lock"))
    if not instance_lock.tryLock(100):
        print("SIDHU AI is already running. Open it from the system tray.", file=sys.stderr)
        from .supervisor import ALREADY_RUNNING
        return ALREADY_RUNNING
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet("QWidget {background:#0b1420; color:#dbe9ed; font-family:Segoe UI; font-size:13px} QLineEdit,QTextEdit {background:#111f2d; border:1px solid #294154; border-radius:8px; padding:10px} QPushButton {background:#173a42; border:1px solid #2f766f; border-radius:6px; padding:10px} QPushButton:hover {background:#245861} QLabel {padding:4px}")
    window = Window()
    return app.exec()


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
