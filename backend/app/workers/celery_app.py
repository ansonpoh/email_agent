from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "email_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

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
        }
    },
)
