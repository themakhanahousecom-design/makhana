from dataclasses import dataclass
from pathlib import Path
import os
import json
import time
import re
import threading
from urllib.parse import urlparse
import psutil
from .memory import Memory
from .windows import WindowsTools
from .window_control import WindowController
from .browser import BrowserInspector
from .workflows import validate_workflows
from .files import FileTools
from .productivity import Productivity, format_time
from .activity import Activity, operation_label
from .ai import AIClient, AIError
from .intents import app_intent, website_intent, diagnostic_intent, battery_intent


@dataclass
class Result:
    ok: bool
    message: str
    agent: str = "Windows Control"
    elapsed_ms: float = 0.0
    history_warning: str = ""


class Engine:
    def __init__(self, settings, memory: Memory, tools=None, inspector=None, on_progress=lambda message: None, window_controller=None):
        self.settings = settings
        self.memory = memory
        self.tools = tools or WindowsTools()
        self.window_controller = window_controller or WindowController()
        self.cancelled = threading.Event()
        self.ai = AIClient(settings, self.cancelled)
        self.activity = Activity(memory.path.with_name("activity.sqlite3"), lambda: self.settings.history_enabled)
        self.productivity = Productivity(memory.path.with_name("productivity.sqlite3"), lambda: self.settings.productivity_enabled)
        self.files = FileTools(settings, self.cancelled)
        self.inspector = inspector or BrowserInspector(settings)
        self.on_progress = on_progress

    def execute(self, text: str, *, reset_cancellation=True) -> Result:
        if reset_cancellation:
            self.cancelled.clear()
        started = time.perf_counter()
        try:
            result = self._execute(text.strip())
        except Exception as exc:
            result = Result(False, f"{type(exc).__name__}: {exc}", "Orchestrator")
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            self.activity.append(operation_label(text), result.agent, result.ok, result.elapsed_ms)
        except Exception:
            result.history_warning = "Activity metadata could not be saved. Tool outcome is unchanged."
        return result

    def analyze_screen(self, image, question, *, consent=None):
        started = time.perf_counter()
        result = self._tool("Vision", lambda: self.ai.analyze_image(image, question, consent=consent))
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            self.activity.append("analyze screen", "Vision", result.ok, result.elapsed_ms)
        except Exception:
            result.history_warning = "Activity metadata could not be saved. Tool outcome is unchanged."
        return result

    @staticmethod
    def _tool(agent, operation):
        try:
            return Result(True, operation(), agent)
        except Exception as exc:
            return Result(False, f"{type(exc).__name__}: {exc}", agent)

    def _execute(self, text, *, workflow_step=False):
        lowered = text.casefold()
        if not lowered:
            return Result(False, "Enter a command.")
        if lowered in {"cancel", "stop", "ruk jao", "ਬੰਦ", "रुको"}:
            self.cancelled.set()
            return Result(True, "Cancellation requested. Already dispatched Windows actions cannot be undone.")
        if self.cancelled.is_set():
            return Result(False, "Workflow cancelled before this step." if workflow_step else "Command cancelled before execution.", "Workflow" if workflow_step else "Planner")
        if lowered in {"capture screen", "analyze screen"}:
            return Result(False, "Use the desktop Screen control for one-shot capture, preview and explicit image-sharing approval. CLI and workflows cannot capture screens.", "Screen")
        if lowered.startswith("task add "):
            task_id = self.productivity.add_task(text[9:])
            return Result(True, f"Task {task_id} saved locally.", "Productivity")
        if lowered == "tasks":
            tasks = self.productivity.tasks()
            return Result(True, "\n".join(f"{task_id} [{'done' if done else 'open'}] {body}" for task_id, body, done in tasks) or "No tasks. Use task add <text>.", "Productivity")
        task_state = re.fullmatch(r"task (done|reopen) (\d+)", lowered)
        if task_state:
            self.productivity.set_done(int(task_state[2]), task_state[1] == "done")
            return Result(True, f"Task {task_state[2]} marked {task_state[1]}.", "Productivity")
        reminder = re.fullmatch(r"remind in (\d+) minutes? (.+)", text, re.I | re.S)
        if reminder:
            reminder_id, due = self.productivity.add_reminder(int(reminder[1]), reminder[2])
            return Result(True, f"Reminder {reminder_id} saved for {format_time(due)}. Delivery requires the desktop assistant to be running; CLI alone does not deliver reminders.", "Productivity")
        if lowered == "reminders":
            reminders = self.productivity.reminders()
            return Result(True, "\n".join(f"{reminder_id} [{state}] {format_time(due)} — {body}" for reminder_id, body, due, state in reminders) or "No reminders.", "Productivity")
        cancelled_reminder = re.fullmatch(r"cancel reminder (\d+)", lowered)
        if cancelled_reminder:
            self.productivity.cancel_reminder(int(cancelled_reminder[1]))
            return Result(True, f"Reminder {cancelled_reminder[1]} cancelled locally.", "Productivity")
        if lowered == "new conversation":
            self.ai.clear()
            return Result(True, "Temporary AI conversation cleared from memory. Local saved notes were not changed.", "AI")
        if lowered == "ai models":
            return self._tool("AI", lambda: "Models returned by configured provider:\n" + ("\n".join(self.ai.models()) or "No models returned."))
        if lowered.startswith("document ") or lowered.startswith("summarize file "):
            from .documents import DocumentTools
            documents = DocumentTools(self.settings, self.cancelled)
            summary = lowered.startswith("summarize file ")
            path = text[len("summarize file "):] if summary else text[len("document "):]
            return self._tool("Documents", lambda: documents.summarize(path) if summary else documents.preview(path))
        if lowered.startswith("analyze csv "):
            from .data_analysis import DataTools
            return self._tool("Data Analysis", lambda: json.dumps(DataTools(self.settings, self.cancelled).analyze_csv(text[len("analyze csv "):]), ensure_ascii=False, allow_nan=False, indent=2))
        if re.search(r"\b(?:do not|don.t|never)\b|मत\s|ਨਾ\s", lowered):
            return Result(False, "No action taken: command includes a negation.", "Planner")
        # No shell executor exists. Unknown requests never become executable code.
        if any(word in lowered for word in ("payment", "pay ", "purchase", "transfer money", "otp", "password", "disable security", "delete ", "remove file", "भुगतान", "पासवर्ड", "पैसे भेज", "ਖਰੀਦ", "ਪਾਸਵਰਡ")):
            return Result(False, "This sensitive action is not supported. No action was taken.", "Permissions")
        window_action = re.fullmatch(r"window (minimize|maximize|restore|switch) (.+)", text, re.I | re.S)
        if lowered == "windows" or window_action:
            if not self.settings.window_control_enabled:
                return Result(False, "Window control is disabled. Enable native window controls in Settings.", "Permissions")
            if lowered == "windows":
                return self._tool("Windows Control", lambda: json.dumps(self.window_controller.list_windows(), ensure_ascii=False, indent=2))
            title = window_action[2].strip()
            if len(title) >= 2 and title.startswith('"') and title.endswith('"'):
                title = title[1:-1]
            return self._tool("Windows Control", lambda: self.window_controller.action(title, window_action[1].casefold()))
        if lowered == "supervisor status":
            from .supervisor import read_status
            return self._tool("Diagnostics", lambda: json.dumps(read_status(self.memory.path.parent), ensure_ascii=False, indent=2))
        if lowered == "history":
            return Result(True, json.dumps(self.activity.list(), ensure_ascii=False, indent=2), "Activity")
        if lowered == "hardware":
            from .diagnostics import hardware_report
            return Result(True, json.dumps(hardware_report(), ensure_ascii=False, indent=2), "Diagnostics")
        if lowered == "processes":
            from .diagnostics import process_report
            return Result(True, json.dumps(process_report(), ensure_ascii=False, indent=2), "Diagnostics")
        if lowered.startswith("run workflow ") and not workflow_step:
            return self.run_workflow(text[len("run workflow "):])
        if lowered == "workflows":
            workflows = validate_workflows(self.settings.workflows)
            return Result(True, "\n".join(f"{name}: {len(steps)} steps" for name, steps in workflows.items()) or "No saved workflows. Create one in Workflows.", "Workflow")
        if lowered.startswith("read "):
            return Result(True, self.files.read(text[5:]), "Files")
        if lowered.startswith("search text "):
            return Result(True, self.files.search_content(text[12:]), "Files")
        if lowered == "recent files":
            return Result(True, self.files.recent(), "Files")
        if lowered == "duplicates":
            return Result(True, self.files.duplicates(), "Files")
        if lowered.startswith("inspect "):
            url = text[len("inspect "):].strip()
            return Result(True, self.inspector.inspect(url, self.cancelled).format(), "Browser")
        if lowered in {"help", "commands"}:
            return Result(True, "Commands: open Chrome/Edge/Explorer/Notepad; open https://example.com; diagnostics; battery; volume 50; latest PDF; find report; remember <note>; memories; ask <question>; inspect https://example.com; workflows; run workflow <name>; read <path>; search text <query>; recent files; duplicates; task add <text>; tasks; task done/reopen <id>; remind in <N> minutes <text>; reminders; cancel reminder <id>; hardware; processes; history; ai models; new conversation; document <path>; summarize file <path>; analyze csv <path>; supervisor status; windows; window minimize/maximize/restore/switch <exact title>; capture screen (desktop approval required).", "Planner")
        if lowered in {"time", "what time is it", "tell me the time"}:
            from datetime import datetime
            now = datetime.now().astimezone()
            return Result(True, now.strftime("It is %I:%M %p on %A, %d %B %Y (%Z)."), "Clock")
        if lowered.startswith("remember "):
            if not self.settings.memory_enabled:
                return Result(False, "Memory is disabled. Enable it in settings before saving a note.", "Memory")
            self.memory.add(text[9:])
            return Result(True, "Note saved locally. Do not store credentials or sensitive information.", "Memory")
        if lowered == "memories":
            if not self.settings.memory_enabled:
                return Result(False, "Memory is disabled.", "Memory")
            return Result(True, "\n".join(f"{i}: {body}" for i, body in self.memory.list()) or "No saved notes.", "Memory")
        if lowered.startswith("ask "):
            return self.ask(text[4:])
        url = website_intent(text)
        if url:
            parsed = urlparse(url)
            if parsed.scheme.casefold() != "https" or not parsed.hostname or parsed.username or parsed.password:
                return Result(False, "Use an HTTPS URL without embedded credentials.", "Browser")
            return Result(True, self.tools.website(url), "Browser")
        if diagnostic_intent(text):
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage(Path.home().anchor)
            return Result(True, f"CPU {psutil.cpu_percent(interval=0.15)}%; RAM {vm.percent}% of {vm.total / 1024**3:.1f} GiB; disk {disk.percent}% used. These readings alone do not identify the cause of slow performance.", "Diagnostics")
        if battery_intent(text):
            battery = psutil.sensors_battery()
            return Result(True, f"Battery {battery.percent}% — {'plugged in' if battery.power_plugged else 'on battery'}." if battery else "No battery sensor is available.", "Diagnostics")
        app = app_intent(text)
        if app:
            if app not in self.settings.allowed_apps:
                return Result(False, f"{app} is not allowed in settings.", "Permissions")
            return Result(True, self.tools.launch(app))
        level = re.fullmatch(r"volume\s+(\d{1,3})", lowered)
        if level:
            value = int(level[1])
            if not 0 <= value <= 100:
                return Result(False, "Volume must be between 0 and 100.")
            return Result(True, self.tools.volume(value))
        if lowered == "latest pdf" or lowered.startswith("find "):
            query = ".pdf" if lowered == "latest pdf" else text[5:]
            return Result(True, self.files.find(query, pdf_only=lowered == "latest pdf"), "Files")
        return Result(False, "Command not recognized. Type help for implemented commands, or ask <question> for a configured AI provider.", "Planner")

    def run_workflow(self, name):
        workflows = validate_workflows(self.settings.workflows)
        key = name.strip().casefold()
        if key not in workflows:
            return Result(False, "No saved workflow with that name.", "Workflow")
        steps = list(workflows[key])
        outcomes = []
        for index, step in enumerate(steps, 1):
            if self.cancelled.is_set():
                return Result(False, "Workflow cancelled. Completed actions were not undone.\n" + "\n".join(outcomes), "Workflow")
            self.on_progress(f"Workflow {key}: step {index}/{len(steps)} — {step}")
            try:
                result = self._execute(step, workflow_step=True)
            except Exception as exc:
                result = Result(False, f"{type(exc).__name__}: {exc}")
            outcomes.append(f"{index}/{len(steps)} [{'OK' if result.ok else 'FAILED'}] {step}\n{result.message}")
            if not result.ok:
                return Result(False, "Workflow stopped at the failed step.\n" + "\n".join(outcomes), "Workflow")
        if self.cancelled.is_set():
            return Result(False, "Workflow cancellation requested after final step; dispatched actions cannot be undone.\n" + "\n".join(outcomes), "Workflow")
        return Result(True, "Workflow completed. Individual dispatch limitations still apply.\n" + "\n".join(outcomes), "Workflow")

    def ask(self, prompt):
        try:
            return Result(True, self.ai.chat(prompt), "AI")
        except AIError as exc:
            return Result(False, str(exc), "AI")
