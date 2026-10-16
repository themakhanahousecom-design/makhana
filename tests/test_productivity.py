import pytest
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory
from sidhu.productivity import Productivity, ReminderScheduler


@pytest.fixture
def store(tmp_path):
    now = [1000.0]
    store = Productivity(tmp_path / 'productivity.db', lambda: True, clock=lambda: now[0])
    return store, now


def test_disabled_productivity_never_creates_database(tmp_path):
    path = tmp_path / 'absent.db'
    store = Productivity(path, lambda: False)
    with pytest.raises(RuntimeError, match='disabled'):
        store.add_task('test')
    ReminderScheduler(store, lambda *args: pytest.fail('disabled scheduler ran')).tick()
    assert not path.exists()


def test_tasks_complete_reopen_and_persist(store):
    db, _ = store
    task_id = db.add_task("Project's first task")
    db.set_done(task_id)
    reopened = Productivity(db.path, lambda: True)
    assert reopened.tasks() == [(task_id, "Project's first task", 1)]
    reopened.set_done(task_id, False)
    assert db.tasks()[0][2] == 0
    with pytest.raises(ValueError, match='does not exist'):
        db.set_done(999)


def test_reminder_due_restart_and_dispatch_exactly_once_in_normal_operation(store):
    db, now = store
    reminder_id, due = db.add_reminder(2, 'Review project')
    assert due == 1120.0 and db.due() == []
    now[0] = 1200.0
    reopened = Productivity(db.path, lambda: True, clock=lambda: now[0])
    notifications = []
    scheduler = ReminderScheduler(reopened, lambda *args: notifications.append(args))
    scheduler.tick()
    scheduler.tick()
    assert notifications == [(reminder_id, 'Review project', 1120.0)]
    assert db.reminders()[0][3] == 'dispatched'


def test_failed_dispatch_remains_pending_for_retry(store):
    db, now = store
    db.add_reminder(1, 'test')
    now[0] += 61
    errors = []
    def fail(*args):
        raise RuntimeError('notifications unavailable')
    scheduler = ReminderScheduler(db, fail, errors.append)
    scheduler.tick()
    assert db.reminders()[0][3] == 'pending'
    assert 'retained for retry' in errors[0]
    scheduler.notify = lambda *args: None
    scheduler.tick()
    assert db.reminders()[0][3] == 'dispatched'


def test_cancelled_reminder_does_not_dispatch(store):
    db, now = store
    reminder_id, _ = db.add_reminder(1, 'cancel this')
    db.cancel_reminder(reminder_id)
    now[0] += 100
    ReminderScheduler(db, lambda *args: pytest.fail('cancelled reminder delivered')).tick()
    assert db.reminders()[0][3] == 'cancelled'


@pytest.mark.parametrize('minutes,text', [(0, 'test'), (-1, 'test'), (525601, 'test'), (1, ''), (1, 'a'*4001)])
def test_invalid_reminder_never_creates_storage(tmp_path, minutes, text):
    path = tmp_path / 'absent.db'
    db = Productivity(path, lambda: True)
    with pytest.raises(ValueError):
        db.add_reminder(minutes, text)
    assert not path.exists()


def test_productivity_content_is_never_an_executable_instruction(tmp_path):
    settings = Settings(productivity_enabled=True)
    engine = Engine(settings, Memory(tmp_path / 'memory.db'))
    assert engine.execute('task add open Chrome').ok
    assert engine.execute('remind in 5 minutes open Chrome').ok
    assert engine.productivity.tasks() == [(1, 'open Chrome', 0)]
    assert 'open Chrome' in engine.execute('reminders').message
    assert engine.execute('task done 1').ok
    assert engine.execute('task reopen 1').ok
    assert engine.execute('cancel reminder 1').ok
    engine.productivity.clear()
    assert engine.productivity.tasks() == []
    assert engine.productivity.reminders() == []


def test_reminder_and_task_bodies_are_stored_as_data_not_sensitive_actions(tmp_path):
    engine = Engine(Settings(productivity_enabled=True), Memory(tmp_path / 'memory.db'))
    assert engine.execute('task add do not open Chrome').ok
    assert engine.execute('remind in 5 minutes update my password').ok
    assert engine.productivity.tasks()[0][1] == 'do not open Chrome'
    assert engine.productivity.reminders()[0][1] == 'update my password'
