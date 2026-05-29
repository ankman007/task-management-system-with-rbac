import os
from celery import Celery

REDIS_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")

celery_app = Celery(
    "worker", broker=REDIS_URL, backend=REDIS_URL, include=["app.tasks.email_tasks"]
)

celery_app.autodiscover_tasks(["app.tasks"])

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
)
