
from celery import Celery
from datetime import datetime, timezone
from sqlalchemy import delete
from src.database.session_db import AsyncSessionLocal  # reuse your session maker

celery = Celery("worker", broker="redis://localhost:6379/0")  # adjust broker
celery.conf.beat_schedule = {
    "cleanup-expired-tokens-every-10-min": {
        "task": "src.tasks.cleanup_expired_tokens",
        "schedule": 600.0,  # every 10 minutes
    },
}
celery.conf.timezone = "UTC"
