"""Read-only host diagnostics without assuming a particular PC configuration.

Byte values describe the current OS-visible host (which can be a virtual machine).
Optional sensors are reported as unavailable rather than filled with example data.
"""

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import platform
import json
import subprocess

import psutil


_WINDOWS_GPU_COMMAND = (
    "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
    "Get-CimInstance -ClassName Win32_VideoController -ErrorAction Stop | "
    "Select-Object Name,VideoProcessor,AdapterRAM,DriverVersion | "
    "ConvertTo-Json -Compress"
)
_READ_ERRORS = (psutil.Error, OSError, NotImplementedError, AttributeError)
_PROCESS_SCAN_LIMIT = 10000


def _number(value):
    """Keep unavailable or non-finite OS readings JSON-safe."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return value if math.isfinite(value) else None


def _unavailable(reason):
    return {"available": False, "reason": reason}


def _read(reader):
    try:
        return {"available": True, **reader()}
    except _READ_ERRORS as exc:
        return _unavailable(f"{type(exc).__name__}: host reading unavailable")


def _cpu():
    result = {
        "logical_cores": psutil.cpu_count(logical=True),
        "physical_cores": psutil.cpu_count(logical=False),
        "usage_percent": _number(psutil.cpu_percent(interval=0.1)),
        "usage_sample_seconds": 0.1,
    }
    try:
        frequency = psutil.cpu_freq()
        result["frequency"] = (
            {"available": True, "current_mhz": _number(frequency.current),
             "minimum_mhz": _number(frequency.min), "maximum_mhz": _number(frequency.max)}
            if frequency else _unavailable("CPU frequency is not exposed by this host")
        )
    except _READ_ERRORS:
        result["frequency"] = _unavailable("CPU frequency is not exposed by this host")
    return result


def _memory():
    memory = psutil.virtual_memory()
    return {"total_bytes": memory.total, "available_bytes": memory.available,
            "used_bytes": memory.used, "usage_percent": _number(memory.percent)}


def _disk():
    root = Path.home().anchor or os.path.abspath(os.sep)
    disk = psutil.disk_usage(root)
    return {"path": root, "total_bytes": disk.total, "used_bytes": disk.used,
            "free_bytes": disk.free, "usage_percent": _number(disk.percent)}


def _battery():
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return _unavailable("No battery sensor is exposed by this host")
        seconds = _number(battery.secsleft)
        return {"available": True, "percent": _number(battery.percent),
                "power_plugged": battery.power_plugged,
                "seconds_left": seconds if seconds is not None and seconds >= 0 else None}
    except _READ_ERRORS:
        return _unavailable("Battery readings are not supported or accessible on this host")


def _temperatures():
    reader = getattr(psutil, "sensors_temperatures", None)
    if reader is None:
        return _unavailable("Temperature sensors are not supported on this platform")
    try:
        sensors = []
        for group, entries in reader().items():
            for entry in entries:
                current = _number(entry.current)
                if current is not None:
                    sensors.append({"group": group, "label": entry.label,
                                    "current_celsius": current,
                                    "high_celsius": _number(entry.high),
                                    "critical_celsius": _number(entry.critical)})
        return ({"available": True, "sensors": sensors} if sensors else
                _unavailable("No readable temperature sensors are exposed by this host"))
    except _READ_ERRORS:
        return _unavailable("Temperature sensors are not supported or accessible on this host")


def _gpu(system):
    if system != "Windows":
        return _unavailable("GPU inventory is currently supported only on Windows")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_GPU_COMMAND],
            shell=False, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode:
            return _unavailable("Windows GPU inventory command failed")
        parsed = json.loads(completed.stdout.lstrip("\ufeff"))
        if isinstance(parsed, dict):
            parsed = [parsed]
        if not isinstance(parsed, list) or not parsed:
            return _unavailable("Windows did not report any video adapters")
        adapters = []
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            adapters.append({
                "name": entry.get("Name"), "video_processor": entry.get("VideoProcessor"),
                "driver_version": entry.get("DriverVersion"),
                "reported_adapter_ram_bytes": _number(entry.get("AdapterRAM")),
            })
        if not adapters:
            return _unavailable("Windows did not report any readable video adapters")
        return {"available": True, "source": "Win32_VideoController", "adapters": adapters,
                "memory_note": "AdapterRAM is an OS-reported 32-bit field and may not reflect full dedicated GPU memory."}
    except subprocess.TimeoutExpired:
        return _unavailable("Windows GPU inventory timed out after 5 seconds")
    except (OSError, ValueError, TypeError):
        return _unavailable("Windows GPU inventory is not available or returned an unreadable response")


def hardware_report():
    """Return JSON-serializable hardware readings for the actual current host.

    The CPU reading samples 0.1 seconds. Windows video inventory has a five-second
    timeout. No hardware controls, privileged commands, or network calls are used.
    """
    system = platform.system()
    report = {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "system": {"name": system, "release": platform.release(),
                   "version": platform.version(), "machine": platform.machine(),
                   "processor": platform.processor() or None,
                   "python_version": platform.python_version()},
        "cpu": _read(_cpu), "memory": _read(_memory), "disk": _read(_disk),
        "battery": _battery(), "temperatures": _temperatures(), "gpu": _gpu(system),
    }
    report["capabilities"] = {
        "read_only": True,
        "windows_gpu_inventory": system == "Windows",
        "battery_readings": report["battery"]["available"],
        "temperature_readings": report["temperatures"]["available"],
        "gpu_inventory": report["gpu"]["available"],
    }
    return report


def process_report(limit=10):
    """Return a bounded process snapshot ordered by resident memory usage.

    Process names/status, memory and accumulated CPU time are read without command
    lines, environment variables or process control. Fields denied by the OS are
    null. Processes that exit while being inspected are skipped. The scan itself
    is capped at 10,000 entries and output is capped at 100 entries.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Process limit must be an integer from 1 to 100")
    rows = []
    skipped = examined = restricted = 0
    scan_truncated = False
    error = None
    try:
        processes = psutil.process_iter(attrs=["pid", "name", "status", "memory_info", "cpu_times"], ad_value=None)
        for process in processes:
            if examined >= _PROCESS_SCAN_LIMIT:
                scan_truncated = True
                break
            examined += 1
            try:
                info = process.info
                memory = info.get("memory_info")
                cpu_times = info.get("cpu_times")
                if any(info.get(field) is None for field in ("name", "status", "memory_info", "cpu_times")):
                    restricted += 1
                rows.append({
                    "pid": info["pid"], "name": info.get("name"), "status": info.get("status"),
                    "memory_rss_bytes": memory.rss if memory else None,
                    "cpu_time_seconds": _number(cpu_times.user + cpu_times.system) if cpu_times else None,
                })
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                skipped += 1
    except _READ_ERRORS as exc:
        error = f"{type(exc).__name__}: process inventory unavailable or incomplete"
    rows.sort(key=lambda row: (-(row["memory_rss_bytes"] or 0), row["pid"]))
    return {
        "available": error is None or bool(rows),
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "processes": rows[:limit], "limit": limit, "order": "resident_memory_descending",
        "examined_count": examined, "skipped_count": skipped,
        "restricted_count": restricted, "scan_limit": _PROCESS_SCAN_LIMIT,
        "truncated": scan_truncated or len(rows) > limit,
        "error": error,
        "capabilities": {"read_only": True, "process_listing": error is None or bool(rows),
                         "platform": platform.system()},
    }
