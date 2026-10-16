"""Native, title-based Windows window operations with observed results.

Importing this module and constructing a controller do not load Windows DLLs.
The small backend interface can be replaced in tests without a Windows session.
"""
from __future__ import annotations

import ctypes
import sys
import time


MAX_WINDOWS = 1000
MAX_TITLE_LENGTH = 32767
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SW_RESTORE = 9
_VERIFY_TIMEOUT = 0.5
_VERIFY_INTERVAL = 0.02

# Use fixed Windows integer widths and pointer-sized handles even in test hosts.
_HWND = ctypes.c_void_p
_BOOL = ctypes.c_int
_DWORD = ctypes.c_uint32
_LPARAM = ctypes.c_ssize_t


class _Win32Backend:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("Window control requires a Windows user session.")
        try:
            self.api = ctypes.WinDLL("user32", use_last_error=True)
        except OSError as exc:
            raise RuntimeError(f"Windows window services could not be loaded: {exc}") from exc
        self._callback_type = ctypes.WINFUNCTYPE(_BOOL, _HWND, _LPARAM)
        signatures = {
            "EnumWindows": ([self._callback_type, _LPARAM], _BOOL),
            "IsWindow": ([_HWND], _BOOL),
            "IsWindowVisible": ([_HWND], _BOOL),
            "GetWindowTextLengthW": ([_HWND], ctypes.c_int),
            "GetWindowTextW": ([_HWND, ctypes.POINTER(ctypes.c_wchar), ctypes.c_int], ctypes.c_int),
            "GetWindowThreadProcessId": ([_HWND, ctypes.POINTER(_DWORD)], _DWORD),
            "IsIconic": ([_HWND], _BOOL),
            "IsZoomed": ([_HWND], _BOOL),
            "GetForegroundWindow": ([], _HWND),
            "ShowWindowAsync": ([_HWND, ctypes.c_int], _BOOL),
            "SetForegroundWindow": ([_HWND], _BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def _error(operation):
        code = ctypes.get_last_error()
        detail = f" (Windows error {code}: {ctypes.FormatError(code).strip()})" if code else ""
        return RuntimeError(f"{operation} failed{detail}.")

    def is_window(self, hwnd):
        return bool(self.api.IsWindow(hwnd))

    def is_visible(self, hwnd):
        return bool(self.api.IsWindowVisible(hwnd))

    def get_title(self, hwnd):
        ctypes.set_last_error(0)
        length = self.api.GetWindowTextLengthW(hwnd)
        if not length and ctypes.get_last_error():
            raise self._error("Reading a window title")
        if length > MAX_TITLE_LENGTH:
            raise RuntimeError("A window title exceeds the supported length.")
        # The title can grow between length/read calls. A fixed bounded buffer
        # avoids matching a truncated prefix as though it were the full title.
        buffer = ctypes.create_unicode_buffer(MAX_TITLE_LENGTH + 1)
        ctypes.set_last_error(0)
        copied = self.api.GetWindowTextW(hwnd, buffer, len(buffer))
        if not copied and ctypes.get_last_error():
            raise self._error("Reading a window title")
        if copied == MAX_TITLE_LENGTH:
            raise RuntimeError("A window title reached the supported length limit.")
        return buffer.value

    def get_pid(self, hwnd):
        pid = _DWORD()
        ctypes.set_last_error(0)
        if not self.api.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            raise self._error("Reading the window process")
        return pid.value

    def list_windows(self):
        windows, errors = [], []
        visited, limited = 0, False

        def visit(hwnd, _parameter):
            nonlocal visited, limited
            visited += 1
            if visited >= MAX_WINDOWS:
                limited = True
                return False
            try:
                if self.is_window(hwnd) and self.is_visible(hwnd):
                    title = self.get_title(hwnd)
                    if title:
                        windows.append({"hwnd": int(hwnd), "title": title, "pid": self.get_pid(hwnd)})
            except Exception as exc:
                # Destruction during enumeration is normal; all other failures
                # must leave the callback normally and be raised in Python.
                if self.is_window(hwnd):
                    errors.append(exc)
                    return False
            return True

        callback = self._callback_type(visit)
        ctypes.set_last_error(0)
        complete = self.api.EnumWindows(callback, 0)
        if errors:
            raise errors[0]
        if limited:
            raise RuntimeError("Window enumeration reached its 1,000-window limit; close unused windows and retry.")
        if not complete:
            raise self._error("Enumerating Windows windows")
        return windows

    def is_iconic(self, hwnd):
        return bool(self.api.IsIconic(hwnd))

    def is_zoomed(self, hwnd):
        return bool(self.api.IsZoomed(hwnd))

    def get_foreground_window(self):
        return int(self.api.GetForegroundWindow() or 0)

    def show_window(self, hwnd, command):
        # Queue the request without waiting on another application's GUI thread.
        # Acceptance alone does not establish that the requested state occurred.
        ctypes.set_last_error(0)
        if not self.api.ShowWindowAsync(hwnd, command):
            raise self._error("Requesting a Windows window state change")

    def set_foreground_window(self, hwnd):
        return bool(self.api.SetForegroundWindow(hwnd))


class WindowController:
    """Operate on one visible window selected by its complete, exact title.

    ``backend`` may supply list_windows, is_window, is_visible, get_title,
    get_pid, is_iconic, is_zoomed, get_foreground_window, show_window, and
    set_foreground_window for tests. It is created lazily when omitted.
    """

    def __init__(self, backend=None):
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            self._backend = _Win32Backend()
        return self._backend

    def list_windows(self) -> list[dict]:
        try:
            backend = self.backend
            windows = backend.list_windows()
            if len(windows) > MAX_WINDOWS:
                raise RuntimeError("Window enumeration exceeded its 1,000-window limit.")
            return [
                {"hwnd": item["hwnd"], "title": item["title"], "pid": item["pid"]}
                for item in windows
                if item["title"] and backend.is_window(item["hwnd"]) and backend.is_visible(item["hwnd"])
            ]
        except OSError as exc:
            raise RuntimeError(f"Listing Windows windows failed: {exc}") from exc

    def _verify_identity(self, window):
        backend, hwnd = self.backend, window["hwnd"]
        if not (
            backend.is_window(hwnd)
            and backend.is_visible(hwnd)
            and backend.get_title(hwnd) == window["title"]
            and backend.get_pid(hwnd) == window["pid"]
        ):
            raise RuntimeError("The selected window changed; list windows and retry.")

    def _wait_for(self, window, observed):
        deadline = time.monotonic() + _VERIFY_TIMEOUT
        while True:
            self._verify_identity(window)
            if observed():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(_VERIFY_INTERVAL, remaining))

    def action(self, title: str, state: str) -> str:
        if state not in {"minimize", "maximize", "restore", "switch"}:
            raise ValueError("Window action must be minimize, maximize, restore, or switch.")
        if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE_LENGTH:
            raise ValueError("Provide a nonempty, complete window title within 32,767 characters.")
        matches = [window for window in self.list_windows() if window["title"] == title]
        if not matches:
            raise RuntimeError(f"No visible window has the exact title {title!r}.")
        if len(matches) != 1:
            raise RuntimeError(f"Multiple visible windows have the exact title {title!r}; use a unique title.")
        backend, window = self.backend, matches[0]
        hwnd = window["hwnd"]
        try:
            self._verify_identity(window)
            if state == "switch":
                if backend.is_iconic(hwnd):
                    backend.show_window(hwnd, SW_RESTORE)
                    if not self._wait_for(window, lambda: not backend.is_iconic(hwnd)):
                        raise RuntimeError(f"Windows did not restore {title!r}; switching was not verified.")
                accepted = backend.set_foreground_window(hwnd)
                if not self._wait_for(window, lambda: backend.get_foreground_window() == hwnd and not backend.is_iconic(hwnd)):
                    if not accepted:
                        raise RuntimeError(f"Windows denied foreground activation for {title!r}.")
                    raise RuntimeError(f"Windows did not make {title!r} the foreground window.")
                return f"Switched to {title!r}; the foreground window was verified."

            backend.show_window(hwnd, {"minimize": SW_MINIMIZE, "maximize": SW_MAXIMIZE, "restore": SW_RESTORE}[state])

            def requested_state():
                minimized, maximized = backend.is_iconic(hwnd), backend.is_zoomed(hwnd)
                return {
                    "minimize": minimized,
                    "maximize": maximized and not minimized,
                    "restore": not minimized and not maximized,
                }[state]

            if not self._wait_for(window, requested_state):
                raise RuntimeError(f"Windows did not confirm the requested {state} state for {title!r}.")
            verb = {"minimize": "Minimized", "maximize": "Maximized", "restore": "Restored"}[state]
            return f"{verb} {title!r}; the window state was verified."
        except OSError as exc:
            raise RuntimeError(f"The Windows window action failed: {exc}") from exc
