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


def test_current_slot_window_midday_uses_previous_same_day_slot():
    user = _user(tz="UTC", times=["09:00", "14:00", "19:00"])
    now_utc = datetime(2026, 5, 25, 14, 0, tzinfo=timezone.utc)

    window = tasks._current_slot_window(user=user, now_utc=now_utc)
    assert window is not None
    assert window["slot_time"] == "14:00"
    assert window["period_start_utc"] == datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)
    assert window["period_end_utc"] == datetime(2026, 5, 25, 14, 0, tzinfo=timezone.utc)


def test_current_slot_window_rolls_over_to_previous_day():
    user = _user(tz="UTC", times=["09:00", "14:00", "19:00"])
    now_utc = datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)

    window = tasks._current_slot_window(user=user, now_utc=now_utc)
    assert window is not None
    assert window["slot_time"] == "09:00"
    assert window["period_start_utc"] == datetime(2026, 5, 24, 19, 0, tzinfo=timezone.utc)
    assert window["period_end_utc"] == datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)


def test_current_slot_window_single_daily_time_uses_previous_day():
    user = _user(tz="UTC", times=["10:30"])
    now_utc = datetime(2026, 5, 25, 10, 30, tzinfo=timezone.utc)

    window = tasks._current_slot_window(user=user, now_utc=now_utc)
    assert window is not None
    assert window["period_start_utc"] == datetime(2026, 5, 24, 10, 30, tzinfo=timezone.utc)
    assert window["period_end_utc"] == datetime(2026, 5, 25, 10, 30, tzinfo=timezone.utc)


def test_run_hourly_cycle_processes_only_users_matching_current_slot(monkeypatch):
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    matching_time = now_utc.strftime("%H:%M")
    non_matching_hour = (now_utc.hour + 1) % 24
    non_matching_time = f"{non_matching_hour:02d}:{now_utc.minute:02d}"

    user_match = _user(tz="UTC", times=[matching_time])
    user_skip = _user(tz="UTC", times=[non_matching_time])
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

    result = tasks.run_hourly_telegram_cycle()
    assert result["status"] == "completed"
    assert result["processed_users"] == 1
    assert result["sent_digests"] == 1
    assert sent_for_users == [str(user_match.id)]
