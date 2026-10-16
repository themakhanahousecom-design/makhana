import json
import os
from types import SimpleNamespace
import subprocess

import psutil
import pytest

from sidhu import diagnostics


def test_hardware_report_reads_actual_host():
    report = diagnostics.hardware_report()
    json.dumps(report, allow_nan=False)
    assert report["cpu"]["available"]
    assert report["cpu"]["logical_cores"] == psutil.cpu_count()
    assert 0 <= report["cpu"]["usage_percent"] <= 100
    assert report["memory"]["total_bytes"] == psutil.virtual_memory().total
    assert report["disk"]["total_bytes"] > 0
    assert report["system"]["name"]
    assert report["capabilities"]["read_only"]


def test_missing_sensors_are_unavailable_without_fabricated_readings(monkeypatch):
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Linux")
    monkeypatch.setattr(psutil, "sensors_battery", lambda: None)
    monkeypatch.delattr(psutil, "sensors_temperatures", raising=False)
    monkeypatch.setattr(psutil, "cpu_freq", lambda: None)
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *a, **kw: pytest.fail("No Windows command on Linux"))
    report = diagnostics.hardware_report()
    for section in ("battery", "temperatures", "gpu"):
        assert report[section]["available"] is False
        assert report[section]["reason"]
    assert not report["cpu"]["frequency"]["available"]
    assert not report["capabilities"]["battery_readings"]
    assert not report["capabilities"]["temperature_readings"]


def test_sensor_access_errors_do_not_abort_hardware_report(monkeypatch):
    def denied():
        raise PermissionError("denied")
    monkeypatch.setattr(psutil, "sensors_battery", denied)
    monkeypatch.setattr(psutil, "sensors_temperatures", denied, raising=False)
    report = diagnostics.hardware_report()
    assert not report["battery"]["available"]
    assert not report["temperatures"]["available"]
    assert report["memory"]["available"]


def test_nonfinite_temperature_and_unknown_battery_time_are_not_invented(monkeypatch):
    monkeypatch.setattr(psutil, "sensors_battery", lambda: SimpleNamespace(percent=70, power_plugged=True, secsleft=psutil.POWER_TIME_UNLIMITED))
    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {"cpu": [SimpleNamespace(label="package", current=48, high=float("nan"), critical=None), SimpleNamespace(label="broken", current=float("nan"), high=None, critical=None)]}, raising=False)
    report = diagnostics.hardware_report()
    assert report["battery"]["seconds_left"] is None
    assert len(report["temperatures"]["sensors"]) == 1
    assert report["temperatures"]["sensors"][0]["high_celsius"] is None
    json.dumps(report, allow_nan=False)


def test_windows_gpu_uses_fixed_read_only_command_and_timeout(monkeypatch):
    calls = []
    def run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0, stdout=json.dumps({"Name": "Actual test adapter", "VideoProcessor": "Test GPU", "AdapterRAM": 2147483648, "DriverVersion": "1.2.3"}))
    monkeypatch.setattr(diagnostics.subprocess, "run", run)
    result = diagnostics._gpu("Windows")
    assert result["available"]
    assert result["adapters"][0]["name"] == "Actual test adapter"
    assert result["adapters"][0]["reported_adapter_ram_bytes"] == 2147483648
    command, options = calls[0]
    assert command[0] == "powershell.exe"
    assert command[-1] == diagnostics._WINDOWS_GPU_COMMAND
    assert "Get-CimInstance -ClassName Win32_VideoController" in command[-1]
    assert options["shell"] is False
    assert options["timeout"] == 5


@pytest.mark.parametrize("failure", ["missing", "timeout", "failure", "invalid_json", "empty"])
def test_windows_gpu_failures_are_unavailable(monkeypatch, failure):
    def run(command, **options):
        if failure == "missing":
            raise FileNotFoundError("powershell unavailable")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, options["timeout"])
        return SimpleNamespace(returncode=1 if failure == "failure" else 0,
                               stdout="bad json" if failure == "invalid_json" else "[]")
    monkeypatch.setattr(diagnostics.subprocess, "run", run)
    result = diagnostics._gpu("Windows")
    assert result["available"] is False
    assert result["reason"]


def test_process_report_reads_real_host_without_process_control():
    report = diagnostics.process_report(limit=100)
    assert report["available"]
    assert 1 <= len(report["processes"]) <= 100
    assert report["examined_count"] <= report["scan_limit"]
    assert report["capabilities"]["read_only"]
    own = next(row for row in report["processes"] if row["pid"] == os.getpid())
    assert own["memory_rss_bytes"] > 0
    assert own["cpu_time_seconds"] >= 0
    assert "cmdline" not in own
    json.dumps(report, allow_nan=False)


def test_processes_that_exit_or_deny_access_are_skipped(monkeypatch):
    class Gone:
        @property
        def info(self):
            raise psutil.NoSuchProcess(987654)
    class Denied:
        @property
        def info(self):
            raise psutil.AccessDenied(987655)
    def process(pid, rss):
        return SimpleNamespace(info={"pid": pid, "name": "test", "status": "sleeping", "memory_info": SimpleNamespace(rss=rss), "cpu_times": SimpleNamespace(user=2.5, system=1.5)})
    monkeypatch.setattr(psutil, "process_iter", lambda **kw: iter([Gone(), process(1, 20), Denied(), process(2, 40)]))
    report = diagnostics.process_report(limit=1)
    assert report["skipped_count"] == 2
    assert report["examined_count"] == 4
    assert report["processes"] == [{"pid": 2, "name": "test", "status": "sleeping", "memory_rss_bytes": 40, "cpu_time_seconds": 4.0}]
    assert report["truncated"]


def test_restricted_process_attributes_remain_unknown(monkeypatch):
    process = SimpleNamespace(info={"pid": 1, "name": None, "status": None, "memory_info": None, "cpu_times": None})
    monkeypatch.setattr(psutil, "process_iter", lambda **kw: iter([process]))
    report = diagnostics.process_report()
    assert report["restricted_count"] == 1
    assert report["processes"][0]["memory_rss_bytes"] is None
    assert report["processes"][0]["cpu_time_seconds"] is None


def test_process_scan_is_bounded(monkeypatch):
    monkeypatch.setattr(diagnostics, "_PROCESS_SCAN_LIMIT", 3)
    def processes(**kw):
        for pid in range(100):
            yield SimpleNamespace(info={"pid": pid, "name": None, "status": None, "memory_info": None, "cpu_times": None})
    monkeypatch.setattr(psutil, "process_iter", processes)
    report = diagnostics.process_report(limit=10)
    assert len(report["processes"]) == 3
    assert report["examined_count"] == 3
    assert report["truncated"]


@pytest.mark.parametrize("limit", [0, -1, 101, True, 1.5, "10"])
def test_process_limit_validation(limit):
    with pytest.raises(ValueError, match="integer from 1 to 100"):
        diagnostics.process_report(limit)
