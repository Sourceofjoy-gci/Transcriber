import json
import subprocess
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.domain import (
    AssetStatus,
    ExportRecord,
    ExportStatus,
    InstalledModel,
    JobAttempt,
    JobEvent,
    JobStatus,
    MediaAsset,
    MediaMetadata,
    ModelCatalog,
    ModelInstallStatus,
    ModelTaskDefault,
    ProviderDefinition,
    ProviderSecret,
    ProviderUsageLog,
    Report,
    Speaker,
    Transcript,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptVersion,
    TranscriptWord,
)
from app.providers.contracts import (
    DiarizationRequest,
    DiarizationResult,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegmentResult,
    TranscriptWordResult,
)
from app.providers.diarization import build_diarization_provider
from app.providers.external import transcribe as external_transcribe
from app.providers.local_whisper import ProviderUnavailableError
from app.providers.registry import build_local_registry
from app.services.exports import render_export, render_report_export
from app.services.provider_secrets import decrypt_secret
from app.services.storage_factory import build_storage_provider
from app.worker.celery_app import celery_app


class JobCancelledError(Exception):
    pass


class ExternalTranscriptionFailed(Exception):
    pass


LOCAL_MODEL_PATH_ADAPTERS = {
    "faster_whisper",
    "whisper_cpp",
    "nemo_asr",
    "nemo_salm",
    "transformers_asr",
    "qwen_asr",
}


@celery_app.task(name="app.worker.tasks.extract_media_metadata", bind=True, max_retries=2)
def extract_media_metadata(self, asset_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        asset = db.get(MediaAsset, UUID(asset_id))
        if asset is None or asset.status == AssetStatus.deleted:
            return {"status": "ignored"}
        asset.status = AssetStatus.processing_metadata
        db.commit()

        try:
            probe = _run_ffprobe(
                settings.ffprobe_path, Path(build_storage_provider(settings).path_for(asset.storage_key))
            )
            parsed = _parse_probe(probe)
        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            asset.status = AssetStatus.failed
            asset.failure_code = "media_metadata_failed"
            asset.failure_message = _safe_error_message(error)
            db.commit()
            raise

        metadata = db.scalar(select(MediaMetadata).where(MediaMetadata.asset_id == asset.id))
        if metadata is None:
            metadata = MediaMetadata(asset_id=asset.id, **parsed)
            db.add(metadata)
        else:
            for field_name, value in parsed.items():
                setattr(metadata, field_name, value)
        asset.status = AssetStatus.ready
        asset.failure_code = None
        asset.failure_message = None
        db.commit()
        _enqueue_derivative_generation(asset.id)
        return {"status": "ready", "asset_id": asset_id, "duration_ms": metadata.duration_ms}


@celery_app.task(name="app.worker.tasks.run_transcription_job", bind=True, max_retries=1)
def run_transcription_job(self, job_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        job = db.get(TranscriptionJob, UUID(job_id))
        if job is None or job.status in {JobStatus.completed, JobStatus.cancelled}:
            return {"status": "ignored"}
        asset = db.get(MediaAsset, job.asset_id)
        if asset is None or asset.status != AssetStatus.ready:
            return _fail_job(db, job, "asset_not_ready", "Media metadata must be ready before transcription")

        attempt = _begin_attempt(db, job)
        storage = build_storage_provider(settings)
        try:
            _advance_job(db, job, JobStatus.extracting_audio, 5, "Preparing audio")
            with tempfile.TemporaryDirectory(prefix="transcriber-") as temporary_directory:
                source_path = Path(storage.path_for(asset.storage_key))
                prepared_path = _prepare_audio(settings.ffmpeg_path, source_path, Path(temporary_directory))
                _advance_job(db, job, JobStatus.preprocessing, 10, "Audio ready for transcription")
                if job.execution_target_kind == "api_provider":
                    _advance_job(
                        db,
                        job,
                        JobStatus.transcribing,
                        12,
                        "Transcribing with external API provider",
                    )
                    provider_key, result = _transcribe_with_api_provider(db, job, prepared_path, settings)
                else:
                    provider_key, options = _resolve_model_options(db, job, settings)
                    registry = build_local_registry(settings)
                    provider = registry.transcription(provider_key)

                    def report_progress(progress: int, message: str, data: dict) -> None:
                        db.refresh(job)
                        if job.cancel_requested_at is not None:
                            raise JobCancelledError()
                        _advance_job(db, job, JobStatus.transcribing, progress, message, data)

                    _advance_job(db, job, JobStatus.transcribing, 12, f"Transcribing with {provider_key}")
                    result = _transcribe_with_chunking(
                        provider,
                        prepared_path,
                        job.language,
                        options,
                        report_progress,
                        _asset_duration_ms(db, asset.id),
                    )
                db.refresh(job)
                if job.cancel_requested_at is not None:
                    raise JobCancelledError()
                result = _apply_configured_diarization(
                    db,
                    job,
                    prepared_path,
                    result,
                    result.duration_ms or _asset_duration_ms(db, asset.id),
                )
                db.refresh(job)
                if job.cancel_requested_at is not None:
                    raise JobCancelledError()
                _advance_job(db, job, JobStatus.post_processing, 96, "Saving transcript")
                transcript = _persist_transcript(db, job, provider_key, result)
                job.status = JobStatus.completed
                job.progress_percent = 100
                job.finished_at = datetime.now(UTC)
                if job.started_at is not None:
                    job.processing_ms = _elapsed_ms(job.started_at, job.finished_at)
                attempt.status = JobStatus.completed
                attempt.finished_at = job.finished_at
                _add_event(
                    db,
                    job,
                    JobStatus.completed,
                    100,
                    "Transcription completed",
                    {"transcript_id": str(transcript.id)},
                )
                db.commit()
                return {"status": "completed", "job_id": job_id, "transcript_id": str(transcript.id)}
        except JobCancelledError:
            job.status = JobStatus.cancelled
            job.finished_at = datetime.now(UTC)
            if job.started_at is not None:
                job.processing_ms = _elapsed_ms(job.started_at, job.finished_at)
            attempt.status = JobStatus.cancelled
            attempt.finished_at = job.finished_at
            _add_event(db, job, JobStatus.cancelled, job.progress_percent, "Transcription cancelled")
            db.commit()
            return {"status": "cancelled", "job_id": job_id}
        except ProviderUnavailableError as error:
            return _fail_job(db, job, "provider_unavailable", str(error), attempt)
        except ExternalTranscriptionFailed as error:
            return _fail_job(db, job, "external_provider_failed", str(error), attempt)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            return _fail_job(db, job, "media_preprocessing_failed", _safe_error_message(error), attempt)
        except Exception as error:
            return _fail_job(
                db, job, "transcription_failed", "Transcription could not be completed", attempt, error
            )


@celery_app.task(name="app.worker.tasks.generate_export", bind=True, max_retries=1)
def generate_export(self, export_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        export = db.get(ExportRecord, UUID(export_id))
        if export is None or export.status == ExportStatus.completed:
            return {"status": "ignored"}
        export.status = ExportStatus.generating
        db.commit()
        try:
            version = db.get(TranscriptVersion, export.transcript_version_id)
            options = export.options or {}
            if options.get("source_type") == "report":
                report_id = options.get("report_id")
                report = db.get(Report, UUID(report_id)) if report_id else None
                if report is None or report.organisation_id != export.organisation_id:
                    raise ValueError("Report export source not found")
                content, media_type, extension = render_report_export(export.format, report, options)
                storage_key = f"organisations/{export.organisation_id}/exports/{export.id}/report.{extension}"
                stored = build_storage_provider(settings).save(
                    _bytes_reader(content), storage_key, max_bytes=50 * 1024 * 1024
                )
                export.storage_key = stored.storage_key
                export.status = ExportStatus.completed
                export.error_message = None
                db.commit()
                return {"status": "completed", "export_id": export_id, "media_type": media_type}
            if version is None:
                raise ValueError("Transcript export source not found")
            segments = list(
                db.scalars(
                    select(TranscriptSegment)
                    .where(TranscriptSegment.version_id == version.id)
                    .order_by(TranscriptSegment.sequence)
                )
            )
            segment_ids = options.get("segment_ids")
            if isinstance(segment_ids, list) and segment_ids:
                selected = {str(segment_id) for segment_id in segment_ids}
                segments = [segment for segment in segments if str(segment.id) in selected]
            speakers = list(db.scalars(select(Speaker).where(Speaker.transcript_id == version.transcript_id)))
            speaker_by_id = {speaker.id: speaker.display_name or speaker.label for speaker in speakers}
            content, media_type, extension = render_export(
                export.format,
                segments,
                export.options,
                speaker_by_id,
            )
            storage_key = f"organisations/{export.organisation_id}/exports/{export.id}/transcript.{extension}"
            stored = build_storage_provider(settings).save(
                _bytes_reader(content), storage_key, max_bytes=50 * 1024 * 1024
            )
            export.storage_key = stored.storage_key
            export.status = ExportStatus.completed
            export.error_message = None
            db.commit()
            return {"status": "completed", "export_id": export_id, "media_type": media_type}
        except Exception:
            export.status = ExportStatus.failed
            export.error_message = "Export generation failed"
            db.commit()
            raise


def _run_ffprobe(ffprobe_path: str, media_path: Path) -> dict:
    completed = subprocess.run(
        [
            ffprobe_path,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(completed.stdout)


def _prepare_audio(ffmpeg_path: str, source_path: Path, temporary_directory: Path) -> Path:
    target_path = temporary_directory / "prepared.wav"
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(target_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    return target_path


def _transcribe_with_chunking(
    provider,
    prepared_path: Path,
    language: str | None,
    options: dict,
    report_progress,
    duration_ms: int | None,
) -> TranscriptionResult:
    chunk_seconds = options.get("chunk_length", 0)
    if (
        not isinstance(chunk_seconds, int)
        or chunk_seconds <= 0
        or duration_ms is None
        or duration_ms <= chunk_seconds * 1000
    ):
        return provider.transcribe(
            TranscriptionRequest(media_path=prepared_path, language=language, options=options),
            report_progress,
        )

    chunk_paths = _split_audio(prepared_path, chunk_seconds)
    chunk_count = len(chunk_paths)
    results: list[TranscriptionResult] = []
    for chunk_index, chunk_path in enumerate(chunk_paths):
        offset_ms = chunk_index * chunk_seconds * 1000

        def chunk_progress(
            progress: int,
            message: str,
            data: dict,
            current_chunk_index: int = chunk_index,
        ) -> None:
            weighted_progress = 12 + int((current_chunk_index + min(1, progress / 100)) / chunk_count * 82)
            report_progress(
                weighted_progress,
                message,
                {**data, "chunk": current_chunk_index + 1, "chunks": chunk_count},
            )

        result = provider.transcribe(
            TranscriptionRequest(media_path=chunk_path, language=language, options=options),
            chunk_progress,
        )
        results.append(_offset_result(result, offset_ms))
    return TranscriptionResult(
        detected_language=next(
            (result.detected_language for result in results if result.detected_language), language
        ),
        duration_ms=duration_ms,
        text=" ".join(result.text for result in results).strip(),
        segments=[segment for result in results for segment in result.segments],
        warnings=["Transcript was processed in fixed-duration chunks"],
    )


def _split_audio(prepared_path: Path, chunk_seconds: int) -> list[Path]:
    output_pattern = prepared_path.parent / "chunk-%04d.wav"
    subprocess.run(
        [
            get_settings().ffmpeg_path,
            "-y",
            "-i",
            str(prepared_path),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-c",
            "copy",
            str(output_pattern),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )
    chunk_paths = sorted(prepared_path.parent.glob("chunk-*.wav"))
    if not chunk_paths:
        raise ValueError("Audio chunking produced no output")
    return chunk_paths


def _offset_result(result: TranscriptionResult, offset_ms: int) -> TranscriptionResult:
    return replace(
        result,
        segments=[
            TranscriptSegmentResult(
                start_ms=segment.start_ms + offset_ms,
                end_ms=segment.end_ms + offset_ms,
                text=segment.text,
                confidence=segment.confidence,
                speaker_label=segment.speaker_label,
                words=[
                    TranscriptWordResult(
                        start_ms=word.start_ms + offset_ms,
                        end_ms=word.end_ms + offset_ms,
                        word=word.word,
                        confidence=word.confidence,
                    )
                    for word in segment.words
                ],
            )
            for segment in result.segments
        ],
    )


def _apply_configured_diarization(
    db,
    job: TranscriptionJob,
    prepared_path: Path,
    result: TranscriptionResult,
    duration_ms: int | None,
) -> TranscriptionResult:
    diarization_options = (job.options or {}).get("diarization")
    if not isinstance(diarization_options, dict) or not diarization_options.get("enabled"):
        return result

    provider = build_diarization_provider(diarization_options.get("provider"))
    provider.validate_options(diarization_options)

    def report_progress(progress: int, message: str, data: dict) -> None:
        db.refresh(job)
        if job.cancel_requested_at is not None:
            raise JobCancelledError()
        _advance_job(
            db,
            job,
            JobStatus.post_processing,
            min(95, max(90, progress)),
            message,
            {"provider": provider.key, **data},
        )

    _advance_job(
        db,
        job,
        JobStatus.post_processing,
        90,
        "Running speaker diarisation",
        {"provider": provider.key},
    )
    diarization = provider.diarize(
        DiarizationRequest(
            media_path=prepared_path,
            duration_ms=duration_ms,
            options=diarization_options,
        ),
        report_progress,
    )
    labelled_result = _apply_diarization_to_result(result, diarization)
    metrics = dict(labelled_result.metrics)
    metrics["diarization"] = {"provider": provider.key, **diarization.metrics}
    return replace(
        labelled_result,
        warnings=[*labelled_result.warnings, *diarization.warnings],
        metrics=metrics,
    )


def _apply_diarization_to_result(
    result: TranscriptionResult, diarization: DiarizationResult
) -> TranscriptionResult:
    if not diarization.segments:
        return result
    return replace(
        result,
        segments=[
            replace(
                segment,
                speaker_label=_best_diarization_label(segment, diarization) or segment.speaker_label,
            )
            for segment in result.segments
        ],
    )


def _best_diarization_label(segment: TranscriptSegmentResult, diarization: DiarizationResult) -> str | None:
    best_label: str | None = None
    best_overlap = 0
    for turn in diarization.segments:
        label = turn.speaker_label.strip()
        if not label:
            continue
        overlap = max(0, min(segment.end_ms, turn.end_ms) - max(segment.start_ms, turn.start_ms))
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    if best_label is not None:
        return best_label

    midpoint = (segment.start_ms + segment.end_ms) // 2
    for turn in diarization.segments:
        if turn.start_ms <= midpoint < turn.end_ms and turn.speaker_label.strip():
            return turn.speaker_label.strip()
    return None


def _asset_duration_ms(db, asset_id: UUID) -> int | None:
    metadata = db.scalar(select(MediaMetadata).where(MediaMetadata.asset_id == asset_id))
    return metadata.duration_ms if metadata else None


def _transcribe_with_api_provider(
    db, job: TranscriptionJob, prepared_path: Path, settings
) -> tuple[str, TranscriptionResult]:
    provider, api_key = _resolve_api_provider(db, job, settings)
    started = time.monotonic()
    try:
        result = external_transcribe(
            provider,
            api_key,
            TranscriptionRequest(media_path=prepared_path, language=job.language, options=job.options),
        )
    except Exception as error:
        duration_ms = max(0, round((time.monotonic() - started) * 1000))
        redacted_error = _redact_external_provider_error(str(error))
        provider.last_error = redacted_error
        provider.last_tested_at = datetime.now(UTC)
        _record_provider_usage(
            db,
            provider.id,
            job.id,
            "failure",
            duration_ms=duration_ms,
            error_code="external_provider_failed",
        )
        raise ExternalTranscriptionFailed(redacted_error) from error

    duration_ms = max(0, round((time.monotonic() - started) * 1000))
    estimated_cost = result.metrics.get("estimated_cost")
    provider.last_error = None
    provider.last_tested_at = datetime.now(UTC)
    job.cost_estimate = str(estimated_cost) if estimated_cost is not None else None
    _record_provider_usage(
        db,
        provider.id,
        job.id,
        "success",
        duration_ms=duration_ms,
        estimated_cost=estimated_cost,
    )
    return provider.adapter_key, result


def _resolve_api_provider(db, job: TranscriptionJob, settings) -> tuple[ProviderDefinition, str | None]:
    if job.execution_target_id is None:
        raise ProviderUnavailableError("Selected API provider is not available")
    provider = db.scalar(
        select(ProviderDefinition).where(
            ProviderDefinition.id == job.execution_target_id,
            ProviderDefinition.organisation_id == job.organisation_id,
        )
    )
    if provider is None or not provider.enabled:
        raise ProviderUnavailableError("Selected API provider is not available")
    if provider.category != "transcription" or not _capabilities_support_transcription(provider.capabilities):
        raise ProviderUnavailableError("Selected API provider does not support transcription")
    if not (provider.model_name or "").strip():
        raise ProviderUnavailableError("Selected API provider must define a model name")
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    api_key = decrypt_secret(settings, secret.ciphertext, secret.nonce) if secret else None
    if provider.auth_type != "none" and not api_key:
        raise ProviderUnavailableError("Selected API provider has no configured credential")
    return provider, api_key


def _record_provider_usage(
    db,
    provider_id: UUID,
    job_id: UUID,
    status: str,
    *,
    duration_ms: int | None = None,
    estimated_cost=None,
    error_code: str | None = None,
) -> None:
    db.add(
        ProviderUsageLog(
            provider_id=provider_id,
            job_id=job_id,
            task="transcription",
            duration_ms=duration_ms,
            estimated_cost=str(estimated_cost) if estimated_cost is not None else None,
            status=status,
            error_code=error_code,
        )
    )


def _capabilities_support_transcription(capabilities: dict | None) -> bool:
    capabilities = capabilities or {}
    if capabilities.get("transcription") is False:
        return False
    tasks = capabilities.get("tasks") or capabilities.get("supported_tasks")
    if tasks is None:
        return True
    if isinstance(tasks, str):
        return tasks == "transcription"
    try:
        return "transcription" in tasks
    except TypeError:
        return False


def _redact_external_provider_error(message: str) -> str:
    lowered = message.lower()
    if "credential" in lowered or "api key" in lowered or "token" in lowered:
        return "External provider credential was rejected or is missing"
    if "timeout" in lowered:
        return "External provider request timed out"
    return "External provider request failed"


def _elapsed_ms(started_at: datetime, finished_at: datetime) -> int:
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        started_at = started_at.replace(tzinfo=finished_at.tzinfo)
    elif finished_at.tzinfo is None and started_at.tzinfo is not None:
        finished_at = finished_at.replace(tzinfo=started_at.tzinfo)
    return max(0, round((finished_at - started_at).total_seconds() * 1000))


def _resolve_model_options(db, job: TranscriptionJob, settings) -> tuple[str, dict]:
    model_id = job.execution_target_id
    if model_id is None and job.execution_target_kind == "automatic":
        default = db.scalar(
            select(ModelTaskDefault).where(
                ModelTaskDefault.organisation_id == job.organisation_id,
                ModelTaskDefault.task == "transcription",
            )
        )
        model_id = default.installed_model_id if default else None
    if model_id is None:
        return job.options.get("provider", settings.default_transcription_provider), {
            **job.options,
            "model_size": job.options.get("model_size", settings.default_transcription_model),
        }
    installed = db.get(InstalledModel, model_id)
    if installed is None or installed.status != ModelInstallStatus.installed or not installed.enabled:
        raise ProviderUnavailableError("Selected local model is not installed and enabled")
    catalog = db.get(ModelCatalog, installed.catalog_id)
    if catalog is None:
        raise ProviderUnavailableError("Selected local model catalog entry is missing")
    compatibility = installed.hardware_compatibility or {}
    if compatibility.get("compatible") is False:
        reasons = compatibility.get("reasons") or [compatibility.get("reason") or "unknown incompatibility"]
        if isinstance(reasons, list):
            reason_text = "; ".join(str(reason) for reason in reasons if reason)
        else:
            reason_text = str(reasons)
        raise ProviderUnavailableError(
            f"Selected local model is incompatible with this worker: {reason_text}"
        )
    options = {**job.options, "model_size": catalog.model_identifier}
    if installed.storage_key:
        model_path = settings.model_root / installed.storage_key
        if catalog.adapter_key in LOCAL_MODEL_PATH_ADAPTERS:
            options["model_path"] = str(model_path)
        elif catalog.adapter_key == "whisper_local":
            options["model_download_root"] = str(model_path)
    installed.last_used_at = datetime.now(UTC)
    db.commit()
    return catalog.adapter_key, options


def _begin_attempt(db, job: TranscriptionJob) -> JobAttempt:
    next_attempt = (
        db.scalar(select(func.max(JobAttempt.attempt_number)).where(JobAttempt.job_id == job.id)) or 0
    ) + 1
    attempt = JobAttempt(
        job_id=job.id,
        attempt_number=next_attempt,
        worker_id=None,
        status=JobStatus.extracting_audio,
        started_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    return attempt


def _advance_job(
    db, job: TranscriptionJob, state: JobStatus, progress: int, message: str, data: dict | None = None
) -> None:
    job.status = state
    job.progress_percent = max(job.progress_percent, min(100, progress))
    if job.started_at is None:
        job.started_at = datetime.now(UTC)
    _add_event(db, job, state, job.progress_percent, message, data)
    db.commit()


def _add_event(
    db, job: TranscriptionJob, state: JobStatus, progress: int, message: str, data: dict | None = None
) -> None:
    sequence = (db.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job.id)) or 0) + 1
    db.add(
        JobEvent(
            job_id=job.id,
            sequence=sequence,
            state=state,
            progress_percent=progress,
            message=message,
            data=data or {},
        )
    )


def _persist_transcript(db, job: TranscriptionJob, provider_key: str, result) -> Transcript:
    transcript = db.scalar(select(Transcript).where(Transcript.job_id == job.id))
    if transcript is None:
        transcript = Transcript(
            job_id=job.id,
            organisation_id=job.organisation_id,
            language=job.language,
            detected_language=result.detected_language,
            source_provider=provider_key,
            status=TranscriptStatus.processing,
        )
        db.add(transcript)
        db.flush()
    next_version = (
        db.scalar(
            select(func.max(TranscriptVersion.version_number)).where(
                TranscriptVersion.transcript_id == transcript.id
            )
        )
        or 0
    ) + 1
    version = TranscriptVersion(
        transcript_id=transcript.id,
        version_number=next_version,
        parent_version_id=transcript.active_version_id,
        created_by_id=None,
        source="transcription_provider",
        change_summary="Initial transcription",
    )
    db.add(version)
    db.flush()
    speakers_by_label = {
        speaker.label: speaker
        for speaker in db.scalars(select(Speaker).where(Speaker.transcript_id == transcript.id))
    }
    for sequence, segment in enumerate(result.segments, start=1):
        speaker = _speaker_for_label(db, transcript, speakers_by_label, segment.speaker_label)
        stored_segment = TranscriptSegment(
            version_id=version.id,
            sequence=sequence,
            start_ms=segment.start_ms,
            end_ms=max(segment.start_ms, segment.end_ms),
            speaker_id=speaker.id if speaker is not None else None,
            text=segment.text,
            confidence=str(segment.confidence) if segment.confidence is not None else None,
        )
        db.add(stored_segment)
        db.flush()
        for word_sequence, word in enumerate(segment.words, start=1):
            db.add(
                TranscriptWord(
                    segment_id=stored_segment.id,
                    sequence=word_sequence,
                    start_ms=word.start_ms,
                    end_ms=max(word.start_ms, word.end_ms),
                    word=word.word,
                    confidence=str(word.confidence) if word.confidence is not None else None,
                )
            )
    transcript.active_version_id = version.id
    transcript.status = TranscriptStatus.completed
    return transcript


def _speaker_for_label(
    db,
    transcript: Transcript,
    speakers_by_label: dict[str, Speaker],
    label: str | None,
) -> Speaker | None:
    normalized_label = _normalize_speaker_label(label)
    if normalized_label is None:
        return None
    speaker = speakers_by_label.get(normalized_label)
    if speaker is not None:
        return speaker
    speaker = Speaker(
        transcript_id=transcript.id,
        label=normalized_label,
        display_name=normalized_label,
    )
    db.add(speaker)
    db.flush()
    speakers_by_label[normalized_label] = speaker
    return speaker


def _normalize_speaker_label(label: str | None) -> str | None:
    if label is None:
        return None
    normalized = label.strip()
    return normalized[:100] or None


def _fail_job(
    db,
    job: TranscriptionJob,
    error_code: str,
    message: str,
    attempt: JobAttempt | None = None,
    exception: Exception | None = None,
) -> dict:
    job.status = JobStatus.failed
    job.error_code = error_code
    job.error_message = message
    job.finished_at = datetime.now(UTC)
    if job.started_at is not None:
        job.processing_ms = _elapsed_ms(job.started_at, job.finished_at)
    if attempt is not None:
        attempt.status = JobStatus.failed
        attempt.finished_at = job.finished_at
        attempt.error_detail = type(exception).__name__ if exception else error_code
    _add_event(db, job, JobStatus.failed, job.progress_percent, message, {"code": error_code})
    db.commit()
    return {"status": "failed", "job_id": str(job.id), "code": error_code}


def _bytes_reader(content: bytes):
    from io import BytesIO

    return BytesIO(content)


def _enqueue_derivative_generation(asset_id: UUID) -> None:
    try:
        from app.worker.media_derivative_tasks import generate_media_derivatives

        generate_media_derivatives.delay(str(asset_id))
    except Exception:
        return


def _parse_probe(probe: dict) -> dict:
    streams = probe.get("streams", [])
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    format_data = probe.get("format", {})
    duration = _parse_duration_ms(format_data.get("duration"))
    return {
        "duration_ms": duration,
        "container": _first_format(format_data.get("format_name")),
        "audio_codec": audio_stream.get("codec_name"),
        "video_codec": video_stream.get("codec_name"),
        "sample_rate_hz": _parse_int(audio_stream.get("sample_rate")),
        "channels": _parse_int(audio_stream.get("channels")),
        "bit_rate": _parse_int(format_data.get("bit_rate") or audio_stream.get("bit_rate")),
        "raw_probe": probe,
    }


def _parse_duration_ms(value: str | int | float | None) -> int | None:
    if value is None:
        return None
    try:
        return max(0, round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


def _parse_int(value: str | int | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _first_format(value: str | None) -> str | None:
    return value.split(",", 1)[0] if value else None


def _safe_error_message(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "FFprobe is not installed or is not available to the worker"
    if isinstance(error, subprocess.TimeoutExpired):
        return "Media metadata extraction timed out"
    if isinstance(error, subprocess.CalledProcessError):
        return "FFprobe could not read this media file"
    return "Media metadata extraction failed"
