from __future__ import annotations

import os
from celery import Celery
from src.config.get_settings import get_settings

settings = get_settings()


def make_celery() -> Celery:
    """
    Factory function — creates Celery app with proper config from settings.
    This is the pattern used by FastAPI docs, Celery docs, and all senior teams.
    """
    celery_app = Celery(
        "movie_app",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=[
            "src.tasks.comment_notifications",  # ← forces import at startup
            "src.tasks.cleanup",
            # add every task module here
        ],
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

    return celery_app


celery_app = make_celery()

# Export for worker/beats
__all__ = ("celery_app",)
