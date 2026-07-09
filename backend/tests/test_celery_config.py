from app.worker.celery_app import celery_app


def test_long_running_model_downloads_are_not_redelivered_early() -> None:
    visibility_timeout = celery_app.conf.broker_transport_options.get("visibility_timeout", 0)
    backend_visibility_timeout = celery_app.conf.result_backend_transport_options.get("visibility_timeout", 0)

    assert visibility_timeout >= 24 * 60 * 60
    assert backend_visibility_timeout >= 24 * 60 * 60
    assert celery_app.conf.worker_prefetch_multiplier == 1
