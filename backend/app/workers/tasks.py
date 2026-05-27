from datetime import datetime, time, timedelta, timezone
import logging
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.db.session import SessionLocal
from app.deps import direct_email_watcher_service, telegram_orchestration_service
from app.models.user import User
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _valid_schedule_time(raw: str) -> bool:
    if len(raw) != 5 or raw[2] != ":":
        return False
    hour_text, minute_text = raw.split(":", 1)
    if not (hour_text.isdigit() and minute_text.isdigit()):
        return False
    hour = int(hour_text)
    minute = int(minute_text)
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _normalized_schedule_times(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if _valid_schedule_time(text):
            out.append(text)
    return sorted(set(out))


def _resolved_timezone(value: str | None):
    zone_name = (value or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _slot_minute_marks(schedule_times: list[str]) -> list[int]:
    return sorted({int(slot[:2]) * 60 + int(slot[3:]) for slot in schedule_times})


def _build_slot_window(
    *,
    user_tz,
    minute_marks: list[int],
    slot_index: int,
    slot_boundary_local: datetime,
) -> dict:
    current_minutes = minute_marks[slot_index]
    previous_minutes = minute_marks[slot_index - 1] if slot_index > 0 else minute_marks[-1]
    previous_date = slot_boundary_local.date() if slot_index > 0 else (slot_boundary_local - timedelta(days=1)).date()
    previous_boundary = datetime.combine(
        previous_date,
        time(hour=previous_minutes // 60, minute=previous_minutes % 60),
        tzinfo=user_tz,
    )
    slot_time = f"{current_minutes // 60:02d}:{current_minutes % 60:02d}"
    return {
        "slot_time": slot_time,
        "local_date": slot_boundary_local.date().isoformat(),
        "period_start_utc": previous_boundary.astimezone(timezone.utc),
        "period_end_utc": slot_boundary_local.astimezone(timezone.utc),
    }


def _due_slot_windows(user: User, now_utc: datetime, grace_minutes: int) -> list[dict]:
    schedule_times = _normalized_schedule_times(user.digest_schedule_times)
    if not schedule_times:
        return []

    user_tz = _resolved_timezone(user.timezone)
    now_local = now_utc.astimezone(user_tz).replace(second=0, microsecond=0)
    grace_window = max(grace_minutes, 0)
    window_start_local = now_local - timedelta(minutes=grace_window)
    minute_marks = _slot_minute_marks(schedule_times)

    candidate_dates = {now_local.date()}
    if window_start_local.date() != now_local.date():
        candidate_dates.add(window_start_local.date())

    due_windows: list[dict] = []
    for candidate_date in sorted(candidate_dates):
        for slot_index, minute_mark in enumerate(minute_marks):
            slot_boundary_local = datetime.combine(
                candidate_date,
                time(hour=minute_mark // 60, minute=minute_mark % 60),
                tzinfo=user_tz,
            )
            if window_start_local <= slot_boundary_local <= now_local:
                due_windows.append(
                    _build_slot_window(
                        user_tz=user_tz,
                        minute_marks=minute_marks,
                        slot_index=slot_index,
                        slot_boundary_local=slot_boundary_local,
                    )
                )

    return sorted(due_windows, key=lambda item: item["period_end_utc"])


@celery_app.task(name="app.workers.tasks.sync_user_emails")
def sync_user_emails(user_id: UUID) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"user_id": str(user_id), "status": "failed", "error": "User not found"}
        result = telegram_orchestration_service.sync_and_analyze(db=db, user=user)
        return {
            "user_id": str(user_id),
            "status": "completed",
            "synced": result["synced"],
            "fetched": result["fetched"],
            "analysed": result["analysed"],
            "urgent_alerts": result["urgent_alerts"],
            "last_checked_at": result["last_checked_at"].isoformat(),
        }
    except Exception as exc:
        logger.exception("sync_user_emails failed for user_id=%s", user_id)
        return {"user_id": str(user_id), "status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.generate_user_digest")
def generate_user_digest(user_id: UUID) -> dict:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"user_id": str(user_id), "status": "failed", "error": "User not found"}
        result = telegram_orchestration_service.generate_and_send_digest(db=db, user=user)
        return {
            "user_id": str(user_id),
            "status": "completed",
            "sent": bool(result.get("sent")),
            "digest_id": result.get("digest_id"),
        }
    except Exception as exc:
        logger.exception("generate_user_digest failed for user_id=%s", user_id)
        return {"user_id": str(user_id), "status": "failed", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.run_hourly_telegram_cycle")
def run_hourly_telegram_cycle() -> dict:
    return run_telegram_cycle()


@celery_app.task(name="app.workers.tasks.run_direct_email_watcher_cycle")
def run_direct_email_watcher_cycle_task() -> dict:
    return run_direct_email_watcher_cycle()


def run_telegram_cycle(*, now_utc: datetime | None = None, grace_minutes: int | None = None) -> dict:
    if not settings.telegram_scheduler_enabled:
        return {"status": "skipped", "reason": "scheduler_disabled"}

    db = SessionLocal()
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    resolved_grace_minutes = max(
        settings.inproc_scheduler_grace_minutes if grace_minutes is None else grace_minutes,
        0,
    )
    completed = 0
    sent_digests = 0
    failed: list[dict] = []

    try:
        users = (
            db.query(User)
            .filter(User.telegram_chat_id.is_not(None))
            .filter(User.scheduled_digest_enabled.is_(True))
            .all()
        )
        for user in users:
            try:
                due_windows = _due_slot_windows(
                    user=user,
                    now_utc=now,
                    grace_minutes=resolved_grace_minutes,
                )
                if not due_windows:
                    continue

                synced_for_user = False
                for slot_window in due_windows:
                    if not synced_for_user:
                        telegram_orchestration_service.sync_and_analyze(db=db, user=user)
                        synced_for_user = True
                    digest = telegram_orchestration_service.generate_and_send_digest(
                        db=db,
                        user=user,
                        run_key=f"{slot_window['local_date']}:{slot_window['slot_time'].replace(':', '')}",
                        job_type="custom_schedule_digest",
                        period_start=slot_window["period_start_utc"],
                        period_end=slot_window["period_end_utc"],
                    )
                    completed += 1
                    if digest.get("sent"):
                        sent_digests += 1
            except Exception as exc:
                db.rollback()
                logger.exception("run_hourly_telegram_cycle user failure user_id=%s", user.id)
                failed.append({"user_id": str(user.id), "error": str(exc)})
        return {
            "status": "completed",
            "processed_users": completed,
            "sent_digests": sent_digests,
            "failed": failed,
        }
    finally:
        db.close()


def run_direct_email_watcher_cycle(*, now_utc: datetime | None = None) -> dict:
    if not settings.direct_email_watcher_enabled:
        return {"status": "skipped", "reason": "direct_email_watcher_disabled"}

    db = SessionLocal()
    try:
        return direct_email_watcher_service.run_cycle(db=db, now_utc=now_utc)
    except Exception as exc:
        logger.exception("run_direct_email_watcher_cycle_failed error=%s", exc)
        return {"status": "failed", "error": str(exc)}
    finally:
        db.close()
