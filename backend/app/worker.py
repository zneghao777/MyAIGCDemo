from celery import Celery
from app.core.logging import configure_logging

configure_logging()
from app.core.config import get_settings

s = get_settings()
celery = Celery("cineai", broker=s.redis_url, backend=s.redis_url, include=["app.tasks.execute"])
celery.conf.update(
    task_default_queue="cineai.script",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_concurrency=s.video_concurrency_limit,
    result_expires=86400,
    timezone="Asia/Shanghai",
    task_track_started=True,
    broker_transport_options={"visibility_timeout": 1800, "global_keyprefix": "cineai:"},
    result_backend_transport_options={"global_keyprefix": "cineai:"},
    beat_schedule={
        "outbox": {"task": "cineai.dispatch", "schedule": 5.0},
        "cleanup": {"task": "cineai.cleanup", "schedule": 60.0},
        "external-media-cleanup": {"task": "cineai.cleanup_external_media", "schedule": 3600.0},
    },
)
