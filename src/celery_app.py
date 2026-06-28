from celery import Celery
from celery.schedules import crontab

from config.dependencies import get_settings

settings = get_settings()

celery_app = Celery(
    "online_cinema",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_BROKER_URL,
    include=["tasks"]
)

celery_app.conf.beat_schedule = {
    "delete-expired-tokens-every-day": {
        "task": "tasks.delete_expired_tokens",
        "schedule": crontab(hour=0, minute=0),  # щодня опівночі
    },
}

celery_app.conf.timezone = "UTC"
