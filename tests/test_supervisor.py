import json
from pathlib import Path
import subprocess
import sys
from sidhu.supervisor import Supervisor, InstanceLock, ALREADY_RUNNING, child_command, read_status


def fake_spawn(codes, commands):
    sequence = iter(codes)
    def spawn(command, **kwargs):
        assert kwargs['shell'] is False
        commands.append(command)
        return type('Child', (), {'wait': lambda self: next(sequence)})()
    return spawn


def test_clean_exit_and_existing_desktop_do_not_restart(tmp_path):
    for code in (0, ALREADY_RUNNING):
        commands, waits = [], []
        supervisor = Supervisor(tmp_path, spawn=fake_spawn([code], commands), command_factory=lambda **flags: flags, wait=waits.append)
        assert supervisor.run() == code
        assert len(commands) == 1 and waits == []
        assert read_status(tmp_path)['events'][-1]['exit_code'] == code


def test_crashes_restart_with_bounded_backoff_and_recovery_mode(tmp_path):
    commands, waits = [], []
    supervisor = Supervisor(tmp_path, spawn=fake_spawn([1, -9, 5, 3], commands), command_factory=lambda **flags: flags, clock=lambda: 0, wait=waits.append)
    assert supervisor.run(background=True) == 1
    assert len(commands) == 4 and waits == [1, 2, 4]
    assert commands[0] == {'background': True, 'recovering': False}
    assert all(command['recovering'] for command in commands[1:])
    assert read_status(tmp_path)['events'][-1]['event'] == 'restart_budget_exhausted'


def test_restart_budget_expires_after_window(tmp_path):
    now = iter([0, 301, 602, 903])
    commands, waits = [], []
    supervisor = Supervisor(tmp_path, spawn=fake_spawn([1, 1, 1, 1, 0], commands), command_factory=lambda **flags: flags, clock=lambda: next(now), wait=waits.append)
    assert supervisor.run() == 0
    assert waits == [1, 1, 1, 1]


def test_lock_blocks_duplicate_and_releases_on_exit(tmp_path):
    with InstanceLock(tmp_path/'lock') as first:
        assert first.acquired
        with InstanceLock(tmp_path/'lock') as second:
            assert not second.acquired
    with InstanceLock(tmp_path/'lock') as third:
        assert third.acquired


def test_actual_child_exit_is_observed_and_metadata_retained(tmp_path):
    # A controlled Python child exits without creating any desktop/audio process.
    supervisor = Supervisor(tmp_path, command_factory=lambda **flags: [sys.executable, '-c', 'raise SystemExit(0)'])
    assert supervisor.run() == 0
    report = read_status(tmp_path)
    assert report['available'] and report['events'][-1]['event'] == 'clean_exit'
    assert 'not a live' in report['note']


def test_command_factory_forwards_only_fixed_internal_flags():
    command = child_command(background=True, recovering=True)
    assert command[0] == sys.executable
    assert command[-3:] == ['--supervised-child', '--background', '--recovering']
    assert '--supervise' not in command


def test_launch_failure_does_not_loop_or_store_exception_contents(tmp_path):
    def fail(*args, **kwargs):
        raise OSError('private executable path')
    supervisor = Supervisor(tmp_path, spawn=fail)
    assert supervisor.run() == 1
    report = read_status(tmp_path)
    assert report['events'][-1]['event'] == 'launch_failed'
    assert 'private executable path' not in json.dumps(report)


def test_missing_status_is_not_a_false_health_claim(tmp_path):
    assert not read_status(tmp_path)['available']


def test_interrupt_during_backoff_does_not_launch_another_child(tmp_path):
    commands = []
    def interrupt(delay):
        raise KeyboardInterrupt
    supervisor = Supervisor(tmp_path, spawn=fake_spawn([1], commands), command_factory=lambda **flags: flags, wait=interrupt)
    assert supervisor.run() == 130
    assert len(commands) == 1
    assert read_status(tmp_path)['events'][-1]['event'] == 'interrupted'


def test_wait_failure_terminates_only_its_own_live_child(tmp_path):
    class Child:
        stopped = False
        def poll(self):
            return 0 if self.stopped else None
        def wait(self, timeout=None):
            if not self.stopped:
                raise OSError('wait failed')
            return 0
        def terminate(self):
            self.stopped = True
    child = Child()
    supervisor = Supervisor(tmp_path, spawn=lambda *args, **kwargs: child)
    assert supervisor.run() == 1
    assert child.stopped


def test_status_cannot_override_non_live_health_note(tmp_path):
    (tmp_path/'supervisor.json').write_text(json.dumps({'events': [], 'available': False, 'note': 'fake live status'}))
    report = read_status(tmp_path)
    assert report['available'] and 'not a live' in report['note']


def test_invalid_cli_combinations_fail_before_launch_or_storage(tmp_path):
    import os
    for arguments in (['--supervise', '--command', 'help'], ['--recovering'], ['--supervise', '--supervised-child']):
        target = tmp_path/'unused-data'
        result = subprocess.run([sys.executable, '-m', 'sidhu.app', *arguments], env={**os.environ, 'SIDHU_DATA_DIR': str(target)}, capture_output=True, text=True, timeout=10)
        assert result.returncode == 2
        assert not target.exists()
