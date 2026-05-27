from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "email_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

direct_email_interval = max(settings.direct_email_watch_interval_minutes, 1)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "hourly-telegram-cycle": {
            "task": "app.workers.tasks.run_hourly_telegram_cycle",
            "schedule": crontab(minute="*"),
        },
        "direct-email-watcher-cycle": {
            "task": "app.workers.tasks.run_direct_email_watcher_cycle",
            "schedule": crontab(minute=f"*/{direct_email_interval}"),
        },
    },
)
