from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.workers import tasks


def _user(*, tz: str, times: list[str]):
    return SimpleNamespace(
        id=uuid4(),
        timezone=tz,
        digest_schedule_times=times,
        scheduled_digest_enabled=True,
        telegram_chat_id="chat-1",
    )


def test_due_slot_window_includes_recent_slot_inside_grace():
    user = _user(tz="UTC", times=["14:00"])
    now_utc = datetime(2026, 5, 25, 14, 10, tzinfo=timezone.utc)

    due_windows = tasks._due_slot_windows(user=user, now_utc=now_utc, grace_minutes=20)
    assert len(due_windows) == 1
    assert due_windows[0]["slot_time"] == "14:00"


def test_due_slot_window_excludes_slot_outside_grace():
    user = _user(tz="UTC", times=["14:00"])
    now_utc = datetime(2026, 5, 25, 14, 25, tzinfo=timezone.utc)

    due_windows = tasks._due_slot_windows(user=user, now_utc=now_utc, grace_minutes=20)
    assert due_windows == []


def test_due_slot_window_crosses_midnight():
    user = _user(tz="UTC", times=["23:55"])
    now_utc = datetime(2026, 5, 26, 0, 5, tzinfo=timezone.utc)

    due_windows = tasks._due_slot_windows(user=user, now_utc=now_utc, grace_minutes=20)
    assert len(due_windows) == 1
    assert due_windows[0]["slot_time"] == "23:55"
    assert due_windows[0]["local_date"] == "2026-05-25"
    assert due_windows[0]["period_end_utc"] == datetime(2026, 5, 25, 23, 55, tzinfo=timezone.utc)


def test_run_cycle_processes_slots_in_grace_window(monkeypatch):
    now_utc = datetime(2026, 5, 25, 14, 10, tzinfo=timezone.utc)

    user_match = _user(tz="UTC", times=["14:00"])
    user_skip = _user(tz="UTC", times=["13:00"])
    users = [user_match, user_skip]

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_conditions):
            return self

        def all(self):
            return self._rows

    class _FakeDb:
        def query(self, _model):
            return _FakeQuery(users)

        @staticmethod
        def rollback():
            return None

        @staticmethod
        def close():
            return None

    sent_for_users: list[str] = []

    def _fake_sync_and_analyze(db, user):
        return {"synced": 0, "fetched": 0, "analysed": 0, "urgent_alerts": 0, "last_checked_at": now_utc}

    def _fake_generate_and_send_digest(db, user, run_key, job_type, period_start, period_end):
        sent_for_users.append(str(user.id))
        return {"sent": True, "digest_id": "d1"}

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(tasks.telegram_orchestration_service, "sync_and_analyze", _fake_sync_and_analyze)
    monkeypatch.setattr(tasks.telegram_orchestration_service, "generate_and_send_digest", _fake_generate_and_send_digest)

    result = tasks.run_telegram_cycle(now_utc=now_utc, grace_minutes=20)
    assert result["status"] == "completed"
    assert result["processed_users"] == 1
    assert result["sent_digests"] == 1
    assert sent_for_users == [str(user_match.id)]


def test_run_cycle_idempotency_when_tick_repeats_same_slot(monkeypatch):
    user = _user(tz="UTC", times=["14:00"])
    users = [user]

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_conditions):
            return self

        def all(self):
            return self._rows

    class _FakeDb:
        def query(self, _model):
            return _FakeQuery(users)

        @staticmethod
        def rollback():
            return None

        @staticmethod
        def close():
            return None

    seen_run_keys: set[str] = set()
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        tasks.telegram_orchestration_service,
        "sync_and_analyze",
        lambda db, user: {"synced": 0, "fetched": 0, "analysed": 0, "urgent_alerts": 0, "last_checked_at": datetime.now(timezone.utc)},
    )

    def _fake_generate_and_send_digest(db, user, run_key, job_type, period_start, period_end):
        if run_key in seen_run_keys:
            return {"sent": False, "skipped_duplicate": True}
        seen_run_keys.add(run_key)
        return {"sent": True, "digest_id": "d1"}

    monkeypatch.setattr(tasks.telegram_orchestration_service, "generate_and_send_digest", _fake_generate_and_send_digest)

    first = tasks.run_telegram_cycle(now_utc=datetime(2026, 5, 25, 14, 10, tzinfo=timezone.utc), grace_minutes=20)
    second = tasks.run_telegram_cycle(now_utc=datetime(2026, 5, 25, 14, 15, tzinfo=timezone.utc), grace_minutes=20)

    assert first["sent_digests"] == 1
    assert second["sent_digests"] == 0
    assert seen_run_keys == {"2026-05-25:1400"}


def test_run_cycle_skips_sending_when_digest_generation_fails(monkeypatch):
    now_utc = datetime(2026, 5, 25, 14, 10, tzinfo=timezone.utc)
    user_match = _user(tz="UTC", times=["14:00"])
    users = [user_match]

    class _FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *_conditions):
            return self

        def all(self):
            return self._rows

    class _FakeDb:
        def query(self, _model):
            return _FakeQuery(users)

        @staticmethod
        def rollback():
            return None

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        tasks.telegram_orchestration_service,
        "sync_and_analyze",
        lambda db, user: {"synced": 0, "fetched": 0, "analysed": 0, "urgent_alerts": 0, "last_checked_at": now_utc},
    )
    monkeypatch.setattr(
        tasks.telegram_orchestration_service,
        "generate_and_send_digest",
        lambda db, user, run_key, job_type, period_start, period_end: {
            "sent": False,
            "reason": "digest_generation_failed",
        },
    )

    result = tasks.run_telegram_cycle(now_utc=now_utc, grace_minutes=20)
    assert result["status"] == "completed"
    assert result["processed_users"] == 1
    assert result["sent_digests"] == 0
    assert result["failed"] == []


def test_run_direct_email_watcher_cycle_disabled(monkeypatch):
    monkeypatch.setattr(tasks.settings, "direct_email_watcher_enabled", False)
    result = tasks.run_direct_email_watcher_cycle()
    assert result["status"] == "skipped"
    assert result["reason"] == "direct_email_watcher_disabled"


def test_run_direct_email_watcher_cycle_runs_service(monkeypatch):
    monkeypatch.setattr(tasks.settings, "direct_email_watcher_enabled", True)

    class _FakeDb:
        @staticmethod
        def close():
            return None

    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDb())
    monkeypatch.setattr(
        tasks.direct_email_watcher_service,
        "run_cycle",
        lambda db, now_utc=None: {"status": "completed", "processed_users": 1, "processed_emails": 2, "created_drafts": 1, "failures": 0},
    )

    result = tasks.run_direct_email_watcher_cycle()
    assert result["status"] == "completed"
    assert result["created_drafts"] == 1
