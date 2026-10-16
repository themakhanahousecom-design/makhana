import ctypes
import sys
from types import SimpleNamespace

import pytest

from sidhu.window_control import MAX_WINDOWS, SW_MAXIMIZE, SW_MINIMIZE, SW_RESTORE, WindowController, _Win32Backend


@pytest.fixture(autouse=True)
def virtual_clock(monkeypatch):
    from sidhu import window_control

    clock = [0.0]
    monkeypatch.setattr(window_control, "time", SimpleNamespace(
        monotonic=lambda: clock[0],
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    ))
    return clock


class FakeBackend:
    def __init__(self, windows=None):
        self.windows = windows if windows is not None else [{"hwnd": 0x123456789, "title": "Document — Notepad", "pid": 100}]
        self.hidden = set()
        self.missing = set()
        self.minimized = set()
        self.maximized = set()
        self.foreground = 0
        self.calls = []
        self.apply_changes = True
        self.accept_focus = True

    def list_windows(self):
        return [dict(window) for window in self.windows]

    def is_window(self, hwnd):
        return hwnd not in self.missing

    def is_visible(self, hwnd):
        return hwnd not in self.hidden

    def get_title(self, hwnd):
        return next(window["title"] for window in self.windows if window["hwnd"] == hwnd)

    def get_pid(self, hwnd):
        return next(window["pid"] for window in self.windows if window["hwnd"] == hwnd)

    def is_iconic(self, hwnd):
        return hwnd in self.minimized

    def is_zoomed(self, hwnd):
        return hwnd in self.maximized

    def show_window(self, hwnd, command):
        self.calls.append(("show", hwnd, command))
        if self.apply_changes:
            self.minimized.discard(hwnd)
            self.maximized.discard(hwnd)
            if command == SW_MINIMIZE:
                self.minimized.add(hwnd)
            elif command == SW_MAXIMIZE:
                self.maximized.add(hwnd)
        return None  # Backend acceptance is not proof of the observed state.

    def set_foreground_window(self, hwnd):
        self.calls.append(("focus", hwnd))
        if self.apply_changes and self.accept_focus:
            self.foreground = hwnd
        return self.accept_focus

    def get_foreground_window(self):
        return self.foreground


def test_backend_is_lazy_and_non_windows_error_is_clear(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    controller = WindowController()
    assert controller._backend is None
    with pytest.raises(RuntimeError, match="Windows user session"):
        controller.list_windows()


def test_lists_only_visible_titled_windows_and_preserves_64bit_handles():
    backend = FakeBackend([
        {"hwnd": 0x123456789, "title": "Document — Notepad", "pid": 100},
        {"hwnd": 2, "title": "", "pid": 101},
        {"hwnd": 3, "title": "Hidden", "pid": 102},
        {"hwnd": 4, "title": "Destroyed", "pid": 103},
    ])
    backend.hidden.add(3)
    backend.missing.add(4)
    windows = WindowController(backend).list_windows()
    assert windows == [{"hwnd": 0x123456789, "title": "Document — Notepad", "pid": 100}]
    windows[0]["title"] = "Caller change"
    assert backend.windows[0]["title"] == "Document — Notepad"


@pytest.mark.parametrize("title", ["Document", "Notepad", "document — notepad", " Document — Notepad"])
def test_only_complete_exact_title_matches(title):
    backend = FakeBackend()
    with pytest.raises(RuntimeError, match="exact title"):
        WindowController(backend).action(title, "minimize")
    assert not backend.calls


def test_ambiguous_titles_reject_before_action():
    backend = FakeBackend([
        {"hwnd": 1, "title": "Untitled", "pid": 100},
        {"hwnd": 2, "title": "Untitled", "pid": 101},
    ])
    with pytest.raises(RuntimeError, match="Multiple visible windows"):
        WindowController(backend).action("Untitled", "maximize")
    assert not backend.calls


@pytest.mark.parametrize("state,command,verb", [("minimize", SW_MINIMIZE, "Minimized"), ("maximize", SW_MAXIMIZE, "Maximized"), ("restore", SW_RESTORE, "Restored")])
def test_native_state_is_observed_after_show_window(state, command, verb):
    backend = FakeBackend()
    hwnd, title = backend.windows[0]["hwnd"], backend.windows[0]["title"]
    if state == "restore":
        backend.minimized.add(hwnd)
        backend.maximized.add(hwnd)
    result = WindowController(backend).action(title, state)
    assert result.startswith(verb) and "verified" in result
    assert backend.calls == [("show", hwnd, command)]


@pytest.mark.parametrize("state", ["minimize", "maximize", "restore"])
def test_unchanged_native_state_does_not_report_success(state):
    backend = FakeBackend()
    backend.apply_changes = False
    if state == "restore":
        backend.maximized.add(backend.windows[0]["hwnd"])
    with pytest.raises(RuntimeError, match="did not confirm"):
        WindowController(backend).action(backend.windows[0]["title"], state)


def test_switch_restores_minimized_window_then_checks_foreground():
    backend = FakeBackend()
    hwnd, title = backend.windows[0]["hwnd"], backend.windows[0]["title"]
    backend.minimized.add(hwnd)
    result = WindowController(backend).action(title, "switch")
    assert "foreground window was verified" in result
    assert backend.calls == [("show", hwnd, SW_RESTORE), ("focus", hwnd)]


def test_switch_rejected_by_windows_is_reported():
    backend = FakeBackend()
    backend.accept_focus = False
    with pytest.raises(RuntimeError, match="denied foreground activation"):
        WindowController(backend).action(backend.windows[0]["title"], "switch")


def test_focus_api_success_without_foreground_change_is_not_success():
    backend = FakeBackend()
    backend.apply_changes = False
    with pytest.raises(RuntimeError, match="did not make.*foreground"):
        WindowController(backend).action(backend.windows[0]["title"], "switch")


def test_failed_restore_does_not_attempt_focus():
    backend = FakeBackend()
    hwnd = backend.windows[0]["hwnd"]
    backend.minimized.add(hwnd)
    backend.apply_changes = False
    with pytest.raises(RuntimeError, match="switching was not verified"):
        WindowController(backend).action(backend.windows[0]["title"], "switch")
    assert backend.calls == [("show", hwnd, SW_RESTORE)]


@pytest.mark.parametrize("change", ["title", "pid", "missing", "hidden"])
def test_identity_changes_between_selection_and_action_are_rejected(change):
    backend = FakeBackend()
    original = backend.list_windows

    def race():
        result = original()
        if change == "title":
            backend.windows[0]["title"] = "A different document"
        elif change == "pid":
            backend.windows[0]["pid"] = 999
        else:
            getattr(backend, change).add(backend.windows[0]["hwnd"])
        return result

    backend.list_windows = race
    with pytest.raises(RuntimeError, match="changed|No visible window"):
        WindowController(backend).action("Document — Notepad", "minimize")
    assert backend.calls == []


def test_enumeration_limit_rejects_incomplete_candidate_set():
    backend = FakeBackend([{"hwnd": n, "title": str(n), "pid": 100} for n in range(MAX_WINDOWS + 1)])
    with pytest.raises(RuntimeError, match="1,000-window limit"):
        WindowController(backend).action("0", "minimize")
    assert not backend.calls


@pytest.mark.parametrize("title,state", [("", "switch"), ("   ", "restore"), (None, "minimize"), ("Title", "close"), ("Title", "type"), ("x" * 32768, "switch")])
def test_invalid_parameters_never_load_windows_backend(title, state):
    controller = WindowController()
    with pytest.raises(ValueError):
        controller.action(title, state)
    assert controller._backend is None


def test_os_error_is_described_without_success():
    backend = FakeBackend()

    def fail(*_args):
        raise OSError("Window station unavailable")

    backend.show_window = fail
    with pytest.raises(RuntimeError, match="Windows window action failed.*Window station"):
        WindowController(backend).action(backend.windows[0]["title"], "minimize")


class NativeFunction:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *args):
        return self.implementation(*args)


def fake_native(monkeypatch, handles):
    state = {"visited": 0, "error": 0}

    def enum(callback, parameter):
        for hwnd in handles:
            state["visited"] += 1
            if not callback(hwnd, parameter):
                return False
        return True

    def text(hwnd, buffer, size):
        buffer.value = f"Window {hwnd}"
        return len(buffer.value)

    def process(hwnd, pointer):
        ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32))[0] = 1234
        return 1

    functions = {
        "EnumWindows": enum,
        "IsWindow": lambda hwnd: True,
        "IsWindowVisible": lambda hwnd: True,
        "GetWindowTextLengthW": lambda hwnd: len(f"Window {hwnd}"),
        "GetWindowTextW": text,
        "GetWindowThreadProcessId": process,
        "IsIconic": lambda hwnd: False,
        "IsZoomed": lambda hwnd: False,
        "GetForegroundWindow": lambda: 0,
        "ShowWindowAsync": lambda *args: True,
        "SetForegroundWindow": lambda hwnd: False,
    }
    api = SimpleNamespace(**{name: NativeFunction(fn) for name, fn in functions.items()})
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: api, raising=False)
    monkeypatch.setattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE, raising=False)
    monkeypatch.setattr(ctypes, "set_last_error", lambda code: state.update(error=code), raising=False)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: state["error"], raising=False)
    return _Win32Backend(), api, state


def test_native_signatures_keep_pointer_sized_handles(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [0x123456789])
    assert api.ShowWindowAsync.argtypes == [ctypes.c_void_p, ctypes.c_int]
    assert api.GetForegroundWindow.restype is ctypes.c_void_p
    assert api.GetWindowThreadProcessId.restype is ctypes.c_uint32
    assert native.list_windows() == [{"hwnd": 0x123456789, "title": "Window 4886718345", "pid": 1234}]


def test_native_enumeration_stops_at_bound(monkeypatch):
    native, _api, state = fake_native(monkeypatch, range(1, MAX_WINDOWS + 100))
    with pytest.raises(RuntimeError, match="1,000-window limit"):
        native.list_windows()
    assert state["visited"] == MAX_WINDOWS


def test_native_enum_failure_is_not_an_empty_success(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [])
    api.EnumWindows.implementation = lambda callback, parameter: False
    with pytest.raises(RuntimeError, match="Enumerating Windows windows failed"):
        native.list_windows()


def test_native_enumeration_does_not_read_hidden_or_empty_titles(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [1, 2, 3])
    api.IsWindowVisible.implementation = lambda hwnd: hwnd != 1
    original_text = api.GetWindowTextW.implementation

    def text(hwnd, buffer, size):
        assert hwnd != 1, "Hidden window titles must not be captured"
        if hwnd == 2:
            buffer.value = ""
            return 0
        return original_text(hwnd, buffer, size)

    api.GetWindowTextW.implementation = text
    assert native.list_windows() == [{"hwnd": 3, "title": "Window 3", "pid": 1234}]


def test_native_callback_failure_is_reported_outside_callback(monkeypatch):
    native, _api, _state = fake_native(monkeypatch, [1, 2])

    def fail(hwnd):
        raise RuntimeError("Cannot read this window title")

    native.get_title = fail
    with pytest.raises(RuntimeError, match="Cannot read this window title"):
        native.list_windows()


def test_native_window_destroyed_during_enumeration_is_skipped(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [1])

    def destroyed(hwnd):
        api.IsWindow.implementation = lambda hwnd: False
        raise RuntimeError("The window was destroyed")

    native.get_title = destroyed
    assert native.list_windows() == []


def test_native_title_at_truncation_bound_is_rejected(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [1])

    def truncated(hwnd, buffer, size):
        buffer.value = "x" * (size - 1)
        return size - 1

    api.GetWindowTextW.implementation = truncated
    with pytest.raises(RuntimeError, match="title reached.*length limit"):
        native.list_windows()


def test_identity_replaced_by_show_window_does_not_report_success():
    backend = FakeBackend()
    original = backend.show_window

    def replaced(hwnd, command):
        original(hwnd, command)
        backend.windows[0]["pid"] = 999

    backend.show_window = replaced
    with pytest.raises(RuntimeError, match="selected window changed"):
        WindowController(backend).action(backend.windows[0]["title"], "minimize")


def test_delayed_window_state_is_observed_with_bounded_polling(virtual_clock):
    backend = FakeBackend()
    backend.apply_changes = False
    observations = []

    def delayed(hwnd):
        observations.append(hwnd)
        return len(observations) >= 3

    backend.is_iconic = delayed
    result = WindowController(backend).action(backend.windows[0]["title"], "minimize")
    assert "verified" in result and len(observations) == 3
    assert virtual_clock[0] == pytest.approx(0.04)


def test_observation_timeout_is_at_most_half_a_second(virtual_clock):
    backend = FakeBackend()
    backend.apply_changes = False
    with pytest.raises(RuntimeError, match="did not confirm"):
        WindowController(backend).action(backend.windows[0]["title"], "minimize")
    assert virtual_clock[0] == pytest.approx(0.5)


def test_delayed_foreground_is_observed_before_success(virtual_clock):
    backend = FakeBackend()
    backend.apply_changes = False
    observations = []
    hwnd = backend.windows[0]["hwnd"]

    def delayed():
        observations.append(True)
        return hwnd if len(observations) >= 3 else 0

    backend.get_foreground_window = delayed
    assert "verified" in WindowController(backend).action(backend.windows[0]["title"], "switch")
    assert len(observations) == 3 and virtual_clock[0] == pytest.approx(0.04)


def test_native_async_request_rejection_is_reported(monkeypatch):
    native, api, _state = fake_native(monkeypatch, [])
    api.ShowWindowAsync.implementation = lambda *args: False
    with pytest.raises(RuntimeError, match="Requesting a Windows window state change failed"):
        native.show_window(1, SW_MINIMIZE)
