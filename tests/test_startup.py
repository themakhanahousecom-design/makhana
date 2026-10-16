import sys
from types import SimpleNamespace
import pytest
from sidhu import windows


class Registry:
    HKEY_CURRENT_USER = 1
    KEY_SET_VALUE = 2
    REG_SZ = 3
    def __init__(self, exists=True):
        self.exists, self.calls = exists, []
    def OpenKey(self, *args):
        if not self.exists:
            raise FileNotFoundError
        return self
    def CreateKeyEx(self, *args):
        self.calls.append('create')
        self.exists = True
        return self
    def DeleteValue(self, key, name):
        self.calls.append(('delete', name))
    def SetValueEx(self, key, name, reserved, kind, value):
        self.calls.append(('set', name, value))
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def test_disabling_stale_startup_does_not_require_interpreter(monkeypatch):
    registry = Registry()
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    monkeypatch.setattr(windows.sys, 'executable', '/missing/python.exe')
    windows.set_autostart(False)
    assert registry.calls == [('delete', 'SidhuAI')]


def test_missing_startup_registry_key_can_be_disabled(monkeypatch):
    registry = Registry(exists=False)
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    windows.set_autostart(False)
    assert registry.calls == []


def test_enable_creates_per_user_key_and_fixed_supervised_command(monkeypatch):
    registry = Registry(exists=False)
    monkeypatch.setitem(sys.modules, 'winreg', registry)
    monkeypatch.setattr(windows.sys, 'platform', 'win32')
    monkeypatch.setattr(windows.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(windows.sys, 'executable', r'C:\User Apps\SIDHU\SidhuAI.exe')
    windows.set_autostart(True)
    assert registry.calls[0] == 'create'
    assert registry.calls[1][2] == '"C:\\User Apps\\SIDHU\\SidhuAI.exe" --supervise --background'
