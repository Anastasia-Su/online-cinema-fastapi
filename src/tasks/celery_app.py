# from celery import Celery

# celery = Celery(
#     "worker",
#     broker="redis://localhost:6379/0",
#     backend="redis://localhost:6379/1",
#     # include=["src.tasks.comment_notifications"]
# )  
# celery.conf.beat_schedule = {
#     "cleanup-expired-tokens-every-5-min": {
#         "task": "cleanup_expired_tokens",
#         "schedule": 600.0,
#     },
# }
# celery.conf.timezone = "UTC"

# src/celery_app.py
from __future__ import annotations

import os
from celery import Celery
from src.config.get_settings import get_settings
# import src.tasks.comment_notifications

# This ensures settings are loaded before Celery starts
settings = get_settings()

def make_celery() -> Celery:
    """
    Factory function — creates Celery app with proper config from settings.
    This is the pattern used by FastAPI docs, Celery docs, and all senior teams.
    """
    celery_app = Celery(
        "movie_app",  # name doesn't matter much
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        # Don't use include= here — better to import tasks explicitly or use autodiscover
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_default_queue="default",
        task_routes={
            "src.tasks.comment_notifications.*": {"queue": "comment_notifications"},
            "src.tasks.cleanup.*": {"queue": "maintenance"},
        },
        beat_schedule={
            "cleanup-expired-tokens-every-hour": {
                "task": "src.tasks.cleanup.cleanup_expired_tokens",  # full path
                "schedule": 3600.0,  # hourly is enough (was 10 min → overkill)
                "options": {"queue": "maintenance"},
            },
        },
    )

    # Optional: autodiscover tasks in src/tasks/
    # celery_app.autodiscover_tasks(["src.tasks"])

    return celery_app


# Create the app instance
celery_app = make_celery()

# Export for worker/beats
__all__ = ("celery_app",)
