from celery import Celery
from celery.signals import task_postrun, task_prerun

from app.core.config import get_settings
from app.core.logging import bind_log_context, clear_log_context, configure_logging

settings = get_settings()
configure_logging(settings.log_format)
LONG_RUNNING_TASK_VISIBILITY_TIMEOUT_SECONDS = 24 * 60 * 60
celery_app = Celery(
    "transcriber",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks", "app.worker.model_tasks", "app.worker.post_processing_tasks"],
)
celery_app.conf.update(
    task_default_queue="maintenance",
    task_routes={
        "app.worker.tasks.extract_media_metadata": {"queue": "media"},
        "app.worker.tasks.run_transcription_job": {"queue": "transcription.cpu"},
        "app.worker.tasks.generate_export": {"queue": "exports"},
        "app.worker.post_processing_tasks.run_ai_processing": {"queue": "exports"},
        "app.worker.post_processing_tasks.generate_report": {"queue": "exports"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_transport_options={"visibility_timeout": LONG_RUNNING_TASK_VISIBILITY_TIMEOUT_SECONDS},
    result_backend_transport_options={"visibility_timeout": LONG_RUNNING_TASK_VISIBILITY_TIMEOUT_SECONDS},
    visibility_timeout=LONG_RUNNING_TASK_VISIBILITY_TIMEOUT_SECONDS,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
celery_app.autodiscover_tasks(["app.worker"])


@task_prerun.connect
def _bind_worker_log_context(task_id=None, task=None, args=None, kwargs=None, **_) -> None:
    job_id = None
    if getattr(task, "name", "") == "app.worker.tasks.run_transcription_job" and args:
        job_id = str(args[0])
    bind_log_context(job_id=job_id or str(task_id))


@task_postrun.connect
def _clear_worker_log_context(**_) -> None:
    clear_log_context()
