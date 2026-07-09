"""Celery tasks for AI post-processing and report generation."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.domain import (
    AIProcessingRun,
    MediaAsset,
    Organisation,
    Project,
    ProviderDefinition,
    ProviderSecret,
    ProviderUsageLog,
    Report,
    ReportTemplate,
    Transcript,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
)
from app.providers.contracts import PostProcessRequest
from app.providers.post_processing import OpenAICompatiblePostProcessingProvider
from app.providers.registry import build_local_registry
from app.services.provider_secrets import decrypt_secret
from app.services.reports import build_report_content
from app.worker.celery_app import celery_app


class AIProcessingCancelled(Exception):
    pass


class AIProviderUnavailable(Exception):
    pass


@celery_app.task(name="app.worker.post_processing_tasks.run_ai_processing", bind=True, max_retries=1)
def run_ai_processing(self, run_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        try:
            run_uuid = UUID(run_id)
        except (TypeError, ValueError):
            return {"status": "ignored"}
        run = db.get(AIProcessingRun, run_uuid)
        if run is None:
            return {"status": "ignored"}
        if run.status in {"completed", "failed", "cancelled"}:
            return {"status": "ignored"}
        run.status = "running"
        run.progress_percent = max(run.progress_percent, 5)
        run.progress_message = "Starting AI processing"
        run.completed_at = None
        run.error_message = None
        db.commit()

        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.version_id == run.transcript_version_id)
                .order_by(TranscriptSegment.sequence)
            )
        )
        full_text = "\n".join(segment.text for segment in segments)
        started = time.monotonic()
        try:
            provider = _resolve_post_processing_provider(db, run, settings)

            def report_progress(progress: int, message: str, data: dict) -> None:
                db.refresh(run)
                if run.cancel_requested_at is not None or run.status == "cancelled":
                    raise AIProcessingCancelled()
                run.progress_percent = min(99, max(0, int(progress)))
                run.progress_message = message[:500] if message else None
                db.commit()

            result = provider.process(
                PostProcessRequest(text=full_text, task=run.task, options=run.options), report_progress
            )
            result_payload = dict(result.result)
            transcript_version_id = _persist_text_output_version(db, run, segments, result.result)
            if transcript_version_id is not None:
                result_payload["transcript_version_id"] = str(transcript_version_id)
            run.result = result_payload
            run.status = "completed"
            run.progress_percent = 100
            run.progress_message = "Completed"
            run.error_message = None
            run.completed_at = datetime.now(UTC)
            if run.execution_target_kind == "api_provider" and run.execution_target_id is not None:
                _record_provider_usage(
                    db,
                    run.execution_target_id,
                    run.task,
                    "success",
                    duration_ms=_elapsed_ms(started),
                    estimated_cost=result.metrics.get("estimated_cost"),
                )
            db.commit()
            return {"status": "completed", "run_id": run_id, "task": run.task}
        except AIProcessingCancelled:
            run.status = "cancelled"
            run.progress_message = "Cancelled"
            run.completed_at = datetime.now(UTC)
            db.commit()
            return {"status": "cancelled", "run_id": run_id}
        except Exception as error:  # noqa: BLE001 - record all failures
            run.status = "failed"
            run.progress_message = "Failed"
            run.error_message = _redact_provider_error(str(error))[:480]
            run.completed_at = datetime.now(UTC)
            if run.execution_target_kind == "api_provider" and run.execution_target_id is not None:
                _record_provider_usage(
                    db,
                    run.execution_target_id,
                    run.task,
                    "failure",
                    duration_ms=_elapsed_ms(started),
                    error_code="ai_provider_failed",
                )
            db.commit()
            return {"status": "failed", "run_id": run_id, "error": run.error_message}


def _resolve_post_processing_provider(db, run: AIProcessingRun, settings):
    if run.execution_target_kind == "api_provider":
        provider, api_key = _resolve_api_provider(db, run, settings)
        return OpenAICompatiblePostProcessingProvider(provider, api_key)
    registry = build_local_registry(settings)
    return registry.post_processing(settings.post_processing_provider)


def _resolve_api_provider(db, run: AIProcessingRun, settings) -> tuple[ProviderDefinition, str | None]:
    if run.execution_target_id is None:
        raise AIProviderUnavailable("Selected API provider is not available")
    _validate_external_policy(db, run)
    provider = db.scalar(
        select(ProviderDefinition).where(
            ProviderDefinition.id == run.execution_target_id,
            ProviderDefinition.organisation_id == run.organisation_id,
        )
    )
    if provider is None or not provider.enabled:
        raise AIProviderUnavailable("Selected API provider is not available")
    if provider.category != "post_processing":
        raise AIProviderUnavailable("Selected API provider does not support AI post-processing")
    if not _capabilities_support_task(provider.capabilities, run.task):
        raise AIProviderUnavailable(f"Selected API provider does not support {run.task}")
    if not (provider.model_name or "").strip():
        raise AIProviderUnavailable("Selected API provider must define a model name")
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    api_key = decrypt_secret(settings, secret.ciphertext, secret.nonce) if secret else None
    if provider.auth_type != "none" and not api_key:
        raise AIProviderUnavailable("Selected API provider has no configured credential")
    return provider, api_key


def _validate_external_policy(db, run: AIProcessingRun) -> None:
    organisation = db.get(Organisation, run.organisation_id)
    if organisation is None or organisation.local_only_enforced or not organisation.external_apis_allowed:
        raise AIProviderUnavailable("External AI processing is disabled by policy")
    version = db.get(TranscriptVersion, run.transcript_version_id)
    transcript = db.get(Transcript, version.transcript_id) if version is not None else None
    job = db.get(TranscriptionJob, transcript.job_id) if transcript is not None else None
    asset = db.get(MediaAsset, job.asset_id) if job is not None else None
    if asset is None or asset.project_id is None:
        return
    project = db.scalar(
        select(Project).where(Project.id == asset.project_id, Project.organisation_id == run.organisation_id)
    )
    if project is not None and project.external_apis_allowed is False:
        raise AIProviderUnavailable("External AI processing is disabled by policy")


def _capabilities_support_task(capabilities: dict | None, task: str) -> bool:
    capabilities = capabilities or {}
    tasks = capabilities.get("tasks") or capabilities.get("supported_tasks")
    if tasks is None:
        return True
    if isinstance(tasks, str):
        return tasks == task
    try:
        return task in tasks
    except TypeError:
        return False


def _persist_text_output_version(
    db,
    run: AIProcessingRun,
    segments: list[TranscriptSegment],
    result: dict,
) -> UUID | None:
    replacement_text = _replacement_text(run.task, result)
    if replacement_text is None:
        return None
    current_version = db.get(TranscriptVersion, run.transcript_version_id)
    if current_version is None:
        raise ValueError("Transcript version no longer exists")
    transcript = db.get(Transcript, current_version.transcript_id)
    if transcript is None:
        raise ValueError("Transcript no longer exists")
    next_version_number = (
        db.scalar(
            select(func.max(TranscriptVersion.version_number)).where(
                TranscriptVersion.transcript_id == transcript.id
            )
        )
        or 0
    ) + 1
    new_version = TranscriptVersion(
        transcript_id=transcript.id,
        version_number=next_version_number,
        parent_version_id=transcript.active_version_id,
        source="ai_processing",
        change_summary=f"AI {run.task} output",
    )
    db.add(new_version)
    db.flush()
    start_ms = segments[0].start_ms if segments else 0
    end_ms = segments[-1].end_ms if segments else 0
    speaker_id = segments[0].speaker_id if len(segments) == 1 else None
    db.add(
        TranscriptSegment(
            version_id=new_version.id,
            sequence=1,
            start_ms=start_ms,
            end_ms=end_ms,
            speaker_id=speaker_id,
            text=replacement_text,
        )
    )
    transcript.active_version_id = new_version.id
    return new_version.id


def _replacement_text(task: str, result: dict) -> str | None:
    if task == "clean":
        value = result.get("cleaned_text") or result.get("text")
    elif task == "translate":
        value = result.get("translation") or result.get("translated_text") or result.get("text")
    else:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AI {task} output did not include transcript text")
    return value.strip()


def _record_provider_usage(
    db,
    provider_id: UUID,
    task: str,
    status: str,
    *,
    duration_ms: int | None = None,
    estimated_cost=None,
    error_code: str | None = None,
) -> None:
    db.add(
        ProviderUsageLog(
            provider_id=provider_id,
            job_id=None,
            task=f"ai:{task}",
            duration_ms=duration_ms,
            estimated_cost=str(estimated_cost) if estimated_cost is not None else None,
            status=status,
            error_code=error_code,
        )
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.monotonic() - started) * 1000))


def _redact_provider_error(message: str) -> str:
    redacted = re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-***", message)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", redacted, flags=re.IGNORECASE)
    return redacted or "AI processing failed"


@celery_app.task(name="app.worker.post_processing_tasks.generate_report", bind=True, max_retries=1)
def generate_report(self, report_id: str) -> dict:
    from uuid import UUID

    settings = get_settings()
    with SessionLocal() as db:
        try:
            report_uuid = UUID(report_id)
        except ValueError:
            return {"status": "ignored"}
        report = db.get(Report, report_uuid)
        if report is None or report.status == "completed":
            return {"status": "ignored"}
        version = db.get(TranscriptVersion, report.transcript_version_id)
        if version is None:
            report.status = "failed"
            db.commit()
            return {"status": "failed", "report_id": report_id}
        report.status = "generating"
        db.commit()
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.version_id == version.id)
                .order_by(TranscriptSegment.sequence)
            )
        )
        transcript = db.get(Transcript, version.transcript_id)
        template = db.get(ReportTemplate, report.template_id) if report.template_id else None
        registry = build_local_registry(settings)
        provider = registry.post_processing(settings.post_processing_provider)
        full_text = "\n".join(segment.text for segment in segments)
        minutes = provider.process(
            PostProcessRequest(text=full_text, task="minutes", options={}), _noop_progress
        ).result
        if transcript is None:
            report.status = "failed"
            db.commit()
            return {"status": "failed", "report_id": report_id}
        content = build_report_content(
            title=report.title,
            transcript=transcript,
            version=version,
            template=template,
            segments=segments,
            minutes=minutes,
        )
        report.content = content
        report.status = "completed"
        db.commit()
        return {"status": "completed", "report_id": report_id}


def _noop_progress(progress: int, message: str, data: dict) -> None:  # pragma: no cover - placeholder
    return None
