import os
from pathlib import Path
import shutil
import subprocess
import sys
import webbrowser


class WindowsTools:
    def require_windows(self):
        if sys.platform != "win32":
            raise RuntimeError("This action requires a Windows user session.")

    def launch(self, name):
        self.require_windows()
        fixed = {"explorer": "explorer.exe", "notepad": "notepad.exe", "chrome": "chrome.exe", "edge": "msedge.exe"}
        exe = shutil.which(fixed[name])
        if not exe:
            candidates = []
            rel = {"chrome": "Google/Chrome/Application/chrome.exe", "edge": "Microsoft/Edge/Application/msedge.exe"}.get(name)
            if rel:
                for root in (os.getenv("PROGRAMFILES"), os.getenv("PROGRAMFILES(X86)"), os.getenv("LOCALAPPDATA")):
                    if root:
                        candidates.append(Path(root) / rel)
            exe = next((str(p) for p in candidates if p.is_file()), None)
        if not exe:
            raise RuntimeError(f"{name} executable was not found. Install it or select another supported application.")
        proc = subprocess.Popen([exe], shell=False)
        return f"Launch request sent to {name} (process {proc.pid}); window readiness is not verified."

    def open_file(self, path):
        self.require_windows()
        os.startfile(str(path))
        return f"Windows accepted the open request for {path.name}; document rendering is not verified."

    def website(self, url):
        self.require_windows()
        if not webbrowser.open(url, new=2):
            raise RuntimeError("The default browser rejected the open request.")
        return f"Browser open request accepted for {url}; page loading is not verified."

    def volume(self, level):
        self.require_windows()
        from pycaw.pycaw import AudioUtilities
        endpoint = AudioUtilities.GetSpeakers().EndpointVolume
        endpoint.SetMasterVolumeLevelScalar(level / 100, None)
        actual = round(endpoint.GetMasterVolumeLevelScalar() * 100)
        return f"Master volume is {actual}%."


def set_autostart(enabled: bool):
    if sys.platform != "win32":
        raise RuntimeError("Sign-in startup requires Windows.")
    import winreg
    registry_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    if not enabled:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_SET_VALUE) as key:
                try:
                    winreg.DeleteValue(key, "SidhuAI")
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        return
    if getattr(sys, "frozen", False):
        args = [sys.executable, "--supervise", "--background"]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.exists():
            raise RuntimeError("pythonw.exe is missing; use the packaged Windows application.")
        args = [str(pythonw), "-m", "sidhu.app", "--supervise", "--background"]
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, registry_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "SidhuAI", 0, winreg.REG_SZ, subprocess.list2cmdline(args))
