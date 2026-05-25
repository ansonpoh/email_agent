from datetime import datetime, time, timedelta, timezone
import logging
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.db.session import SessionLocal
from app.deps import telegram_orchestration_service
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


def _current_slot_window(user: User, now_utc: datetime) -> dict | None:
    schedule_times = _normalized_schedule_times(user.digest_schedule_times)
    if not schedule_times:
        return None

    user_tz = _resolved_timezone(user.timezone)
    now_local = now_utc.astimezone(user_tz).replace(second=0, microsecond=0)
    current_slot = now_local.strftime("%H:%M")
    if current_slot not in schedule_times:
        return None

    minute_marks = sorted({int(slot[:2]) * 60 + int(slot[3:]) for slot in schedule_times})
    current_minutes = int(current_slot[:2]) * 60 + int(current_slot[3:])
    slot_idx = minute_marks.index(current_minutes)
    previous_minutes = minute_marks[slot_idx - 1] if slot_idx > 0 else minute_marks[-1]

    current_boundary = now_local.replace(hour=int(current_slot[:2]), minute=int(current_slot[3:]), second=0, microsecond=0)
    previous_date = current_boundary.date() if slot_idx > 0 else (current_boundary - timedelta(days=1)).date()
    previous_boundary = datetime.combine(
        previous_date,
        time(hour=previous_minutes // 60, minute=previous_minutes % 60),
        tzinfo=user_tz,
    )

    return {
        "slot_time": current_slot,
        "local_date": current_boundary.date().isoformat(),
        "period_start_utc": previous_boundary.astimezone(timezone.utc),
        "period_end_utc": current_boundary.astimezone(timezone.utc),
    }


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
    if not settings.telegram_scheduler_enabled:
        return {"status": "skipped", "reason": "scheduler_disabled"}

    db = SessionLocal()
    now = datetime.now(timezone.utc)
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
                slot_window = _current_slot_window(user=user, now_utc=now)
                if not slot_window:
                    continue
                telegram_orchestration_service.sync_and_analyze(db=db, user=user)
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
