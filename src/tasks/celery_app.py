from celery import Celery

celery = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
)  
celery.conf.beat_schedule = {
    "cleanup-expired-tokens-every-5-min": {
        "task": "cleanup_expired_tokens",
        "schedule": 600.0,
    },
}
celery.conf.timezone = "UTC"
