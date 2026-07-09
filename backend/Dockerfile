FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git libsndfile1 sox \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir -c requirements.lock .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/transcriber/storage /var/lib/transcriber/models \
    && chown -R appuser:appuser /app /var/lib/transcriber

USER appuser
EXPOSE 8000

FROM base AS api
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
USER root
ARG WORKER_EXTRAS=ai
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -c requirements.lock ".[${WORKER_EXTRAS}]"
USER appuser
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO"]
