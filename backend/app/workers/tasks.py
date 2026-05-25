from datetime import datetime, timezone
import logging
from uuid import UUID

from app.config import settings
from app.db.session import SessionLocal
from app.deps import telegram_orchestration_service
from app.models.user import User
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


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
    run_key = now.strftime("%Y%m%d%H")
    completed = 0
    sent_digests = 0
    failed: list[dict] = []

    try:
        users = (
            db.query(User)
            .filter(User.telegram_chat_id.is_not(None))
            .filter(User.digest_frequency == "hourly")
            .all()
        )
        for user in users:
            try:
                telegram_orchestration_service.sync_and_analyze(db=db, user=user)
                digest = telegram_orchestration_service.generate_and_send_digest(
                    db=db,
                    user=user,
                    run_key=run_key,
                    job_type="hourly_digest",
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
            "run_key": run_key,
            "processed_users": completed,
            "sent_digests": sent_digests,
            "failed": failed,
        }
    finally:
        db.close()
