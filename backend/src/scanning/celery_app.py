from celery import Celery

from src.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "file_tasks",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_broker_url,
)
celery_app.autodiscover_tasks(["src.scanning"])
