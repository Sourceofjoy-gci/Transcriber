import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import (
    Speaker,
    Transcript,
    TranscriptAnnotation,
    TranscriptEditOperation,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
    TranscriptWord,
)
from app.schemas.transcripts import (
    AnnotationRequest,
    MergeSegmentsRequest,
    OperationCheckpointRequest,
    SearchHit,
    SearchReplaceRequest,
    SearchReplaceResponse,
    SearchResponse,
    SegmentBatchEditRequest,
    SegmentEditRequest,
    SegmentSpeakerRequest,
    SpeakerRequest,
    SpeakerResponse,
    SpeakerUpdateRequest,
    SplitSegmentRequest,
    TranscriptDetailResponse,
    TranscriptResponse,
    TranscriptSegmentResponse,
    TranscriptVersionResponse,
    VersionRestoreRequest,
)
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/transcripts", tags=["transcripts"])
DbSession = Annotated[Session, Depends(get_db)]
TranscriptReader = Annotated[Principal, Depends(require_permission("transcripts.read"))]
TranscriptEditor = Annotated[Principal, Depends(require_permission("transcripts.edit"))]
SegmentTransform = Callable[[TranscriptSegment], dict]


@router.get("", response_model=list[TranscriptResponse])
def list_transcripts(principal: TranscriptReader, db: DbSession, limit: int = 50) -> list[TranscriptResponse]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid limit")
    transcripts = list(
        db.scalars(
            select(Transcript)
            .where(Transcript.organisation_id == principal.organisation.id)
            .order_by(Transcript.created_at.desc())
            .limit(limit)
        )
    )
    return [_response_for_transcript(db, transcript) for transcript in transcripts]


@router.get("/{transcript_id}", response_model=TranscriptDetailResponse)
def get_transcript(
    transcript_id: uuid.UUID, principal: TranscriptReader, db: DbSession
) -> TranscriptDetailResponse:
    return _detail_for_transcript(db, _get_transcript(db, principal, transcript_id))


@router.patch("/{transcript_id}/segments/{segment_id}", response_model=TranscriptDetailResponse)
def edit_segment(
    transcript_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: SegmentEditRequest,
    request: Request,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptDetailResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source_segments = _source_segments(db, _active_version_id(transcript))
    if not any(segment.id == segment_id for segment in source_segments):
        raise HTTPException(status_code=404, detail="Transcript segment not found")

    version = _create_version_from_segments(
        db,
        transcript,
        principal,
        source_segments,
        operation_type="segment_edit",
        change_summary=payload.change_summary or "Segment text edited",
        operation_segment_id=segment_id,
        payload={
            "segment_id": str(segment_id),
            "text": payload.text,
            "notes": payload.notes,
            "is_unclear": payload.is_unclear,
        },
        transform=lambda source: {
            "text": payload.text,
            "notes": payload.notes,
            "is_unclear": payload.is_unclear if payload.is_unclear is not None else source.is_unclear,
        }
        if source.id == segment_id
        else {},
    )
    write_audit(
        db,
        principal,
        "transcript.segment_edited",
        "transcript",
        transcript.id,
        "success",
        request,
        {"segment_id": str(segment_id), "version_id": str(version.id)},
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/segments:batch-edit", response_model=TranscriptDetailResponse)
def batch_edit_segments(
    transcript_id: uuid.UUID,
    payload: SegmentBatchEditRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptDetailResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source_segments = _source_segments(db, _active_version_id(transcript))
    edits = {edit.segment_id: edit for edit in payload.edits}
    missing = set(edits) - {segment.id for segment in source_segments}
    if missing:
        raise HTTPException(status_code=404, detail="One or more transcript segments were not found")
    for edit in payload.edits:
        _validate_speaker(db, transcript, edit.speaker_id)

    def transform(source: TranscriptSegment) -> dict:
        edit = edits.get(source.id)
        if edit is None:
            return {}
        return {
            "text": edit.text if edit.text is not None else source.text,
            "notes": edit.notes if edit.notes is not None else source.notes,
            "is_unclear": edit.is_unclear if edit.is_unclear is not None else source.is_unclear,
            "speaker_id": edit.speaker_id if edit.speaker_id is not None else source.speaker_id,
        }

    _create_version_from_segments(
        db,
        transcript,
        principal,
        source_segments,
        operation_type="batch_edit",
        change_summary=payload.change_summary or "Autosaved segment edits",
        payload={"edits": [edit.model_dump(mode="json") for edit in payload.edits]},
        transform=transform,
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.get("/{transcript_id}/versions", response_model=list[TranscriptVersionResponse])
def list_versions(transcript_id: uuid.UUID, principal: TranscriptReader, db: DbSession):
    transcript = _get_transcript(db, principal, transcript_id)
    return [
        TranscriptVersionResponse.model_validate(item)
        for item in db.scalars(
            select(TranscriptVersion)
            .where(TranscriptVersion.transcript_id == transcript.id)
            .order_by(TranscriptVersion.version_number.desc())
        )
    ]


@router.post("/{transcript_id}/versions:restore", response_model=TranscriptResponse)
def restore_version(
    transcript_id: uuid.UUID,
    payload: VersionRestoreRequest,
    request: Request,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    target = db.get(TranscriptVersion, payload.version_id)
    if target is None or target.transcript_id != transcript.id:
        raise HTTPException(status_code=404, detail="Version not found")
    previous_id = _active_version_id(transcript)
    transcript.active_version_id = target.id
    _record_operation(
        db,
        transcript,
        principal,
        "version_restore",
        from_version_id=previous_id,
        to_version_id=target.id,
        payload={"version_id": str(target.id)},
    )
    write_audit(
        db,
        principal,
        "transcript.version_restored",
        "transcript",
        transcript.id,
        "success",
        request,
        {"version_id": str(target.id)},
    )
    db.commit()
    return _response_for_transcript(db, transcript)


@router.get("/{transcript_id}/search", response_model=SearchResponse)
def search_transcript(
    transcript_id: uuid.UUID, principal: TranscriptReader, db: DbSession, q: str, limit: int = 50
) -> SearchResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    if transcript.active_version_id is None:
        return SearchResponse(query=q, hits=[])
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="Search query is required")
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Invalid limit")
    needle = f"%{q.strip()}%"
    rows = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.version_id == transcript.active_version_id)
            .where(TranscriptSegment.text.ilike(needle))
            .order_by(TranscriptSegment.sequence)
            .limit(limit)
        )
    )
    hits: list[SearchHit] = []
    needle_lower = q.lower()
    for segment in rows:
        text = segment.text
        idx = text.lower().find(needle_lower)
        if idx < 0:
            snippet_start, snippet_end = 0, min(len(text), 120)
        else:
            snippet_start = max(0, idx - 30)
            snippet_end = min(len(text), snippet_start + 120)
        hits.append(
            SearchHit(
                segment_id=segment.id,
                sequence=segment.sequence,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                snippet=text[snippet_start:snippet_end],
            )
        )
    return SearchResponse(query=q, hits=hits)


@router.post("/{transcript_id}/search:replace", response_model=SearchReplaceResponse)
def replace_search_hits(
    transcript_id: uuid.UUID,
    payload: SearchReplaceRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> SearchReplaceResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source_segments = _source_segments(db, _active_version_id(transcript))
    flags = 0 if payload.case_sensitive else re.IGNORECASE
    pattern = re.compile(re.escape(payload.query), flags)
    replacements: dict[uuid.UUID, str] = {}
    replacement_count = 0
    for segment in source_segments:
        count = 0 if payload.replace_all else max(0, 1 - replacement_count)
        text, changed = pattern.subn(payload.replacement, segment.text, count=count)
        if changed:
            replacements[segment.id] = text
            replacement_count += changed
        if replacement_count and not payload.replace_all:
            break
    if replacement_count:
        _create_version_from_segments(
            db,
            transcript,
            principal,
            source_segments,
            operation_type="search_replace",
            change_summary=f"Replaced {replacement_count} transcript match(es)",
            payload=payload.model_dump(mode="json") | {"replacement_count": replacement_count},
            transform=lambda source: {"text": replacements[source.id]} if source.id in replacements else {},
        )
        db.commit()
    return SearchReplaceResponse(
        transcript=_detail_for_transcript(db, transcript),
        replacement_count=replacement_count,
    )


@router.get("/{transcript_id}/speakers", response_model=list[SpeakerResponse])
def list_speakers(transcript_id: uuid.UUID, principal: TranscriptReader, db: DbSession):
    transcript = _get_transcript(db, principal, transcript_id)
    return [
        SpeakerResponse.model_validate(item)
        for item in db.scalars(
            select(Speaker).where(Speaker.transcript_id == transcript.id).order_by(Speaker.label)
        )
    ]


@router.post("/{transcript_id}/speakers", response_model=SpeakerResponse)
def create_speaker(
    transcript_id: uuid.UUID, payload: SpeakerRequest, principal: TranscriptEditor, db: DbSession
):
    transcript = _get_transcript(db, principal, transcript_id)
    speaker = Speaker(transcript_id=transcript.id, **payload.model_dump())
    db.add(speaker)
    db.commit()
    db.refresh(speaker)
    return SpeakerResponse.model_validate(speaker)


@router.patch("/{transcript_id}/speakers/{speaker_id}", response_model=SpeakerResponse)
def update_speaker(
    transcript_id: uuid.UUID,
    speaker_id: uuid.UUID,
    payload: SpeakerUpdateRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> SpeakerResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    speaker = db.get(Speaker, speaker_id)
    if speaker is None or speaker.transcript_id != transcript.id:
        raise HTTPException(status_code=404, detail="Speaker not found")
    if payload.display_name is not None:
        speaker.display_name = payload.display_name
    if payload.role is not None:
        speaker.role = payload.role
    if payload.color is not None:
        speaker.color = payload.color
    db.commit()
    db.refresh(speaker)
    return SpeakerResponse.model_validate(speaker)


@router.patch("/{transcript_id}/segments/{segment_id}/speaker", response_model=TranscriptDetailResponse)
def assign_segment_speaker(
    transcript_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: SegmentSpeakerRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptDetailResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    _validate_speaker(db, transcript, payload.speaker_id)
    source_segments = _source_segments(db, _active_version_id(transcript))
    if not any(segment.id == segment_id for segment in source_segments):
        raise HTTPException(status_code=404, detail="Transcript segment not found")
    _create_version_from_segments(
        db,
        transcript,
        principal,
        source_segments,
        operation_type="speaker_assign",
        change_summary="Segment speaker assigned",
        operation_segment_id=segment_id,
        payload={
            "segment_id": str(segment_id),
            "speaker_id": str(payload.speaker_id) if payload.speaker_id else None,
        },
        transform=lambda source: {"speaker_id": payload.speaker_id} if source.id == segment_id else {},
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/segments:split", response_model=TranscriptDetailResponse)
def split_segment(
    transcript_id: uuid.UUID, payload: SplitSegmentRequest, principal: TranscriptEditor, db: DbSession
):
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source = _source_segments(db, _active_version_id(transcript))
    target = next(
        (
            item
            for item in source
            if (payload.segment_id is None or item.id == payload.segment_id)
            and item.start_ms < payload.split_at_ms < item.end_ms
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=422, detail="Split time must be inside a segment")
    previous_id = _active_version_id(transcript)
    version = _new_version(db, transcript, principal, "human_edit", "Segment split")
    sequence = 1
    for item in source:
        parts = (
            [(item.start_ms, item.end_ms, item.text)]
            if item.id != target.id
            else [(item.start_ms, payload.split_at_ms, item.text), (payload.split_at_ms, item.end_ms, "")]
        )
        for start_ms, end_ms, text in parts:
            new_segment = _add_segment_copy(
                db,
                version.id,
                item,
                sequence,
                {"start_ms": start_ms, "end_ms": end_ms, "text": text},
            )
            db.flush()
            _copy_words(db, item.id, new_segment.id, start_ms=start_ms, end_ms=end_ms)
            sequence += 1
    transcript.active_version_id = version.id
    _record_operation(
        db,
        transcript,
        principal,
        "segment_split",
        from_version_id=previous_id,
        to_version_id=version.id,
        segment_id=target.id,
        payload=payload.model_dump(mode="json"),
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/segments:merge", response_model=TranscriptDetailResponse)
def merge_segments(
    transcript_id: uuid.UUID, payload: MergeSegmentsRequest, principal: TranscriptEditor, db: DbSession
):
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source = _source_segments(db, _active_version_id(transcript))
    first = next((item for item in source if item.id == payload.first_segment_id), None)
    second = next((item for item in source if item.id == payload.second_segment_id), None)
    if first is None or second is None or second.sequence != first.sequence + 1:
        raise HTTPException(status_code=422, detail="Only adjacent segments can be merged")

    def transform(item: TranscriptSegment) -> dict:
        if item.id == first.id:
            return {"text": f"{first.text} {second.text}".strip(), "end_ms": second.end_ms}
        return {}

    _create_version_from_segments(
        db,
        transcript,
        principal,
        source,
        operation_type="segment_merge",
        change_summary="Segments merged",
        operation_segment_id=first.id,
        payload=payload.model_dump(mode="json"),
        transform=transform,
        skip_segment_ids={second.id},
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/annotations", response_model=TranscriptDetailResponse)
def add_annotation(
    transcript_id: uuid.UUID, payload: AnnotationRequest, principal: TranscriptEditor, db: DbSession
):
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    source = _source_segments(db, _active_version_id(transcript))
    target = next((item for item in source if item.id == payload.segment_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Segment not found in active version")

    def transform(item: TranscriptSegment) -> dict:
        if item.id != target.id:
            return {}
        notes = item.notes or ""
        if payload.note:
            notes = (notes + "\n" + payload.note).strip() if notes else payload.note
        return {
            "notes": notes or None,
            "is_unclear": payload.is_unclear if payload.is_unclear is not None else item.is_unclear,
        }

    version, segment_map = _create_version_from_segments(
        db,
        transcript,
        principal,
        source,
        operation_type="annotation",
        source="annotation",
        change_summary="Segment annotation updated",
        operation_segment_id=target.id,
        payload=payload.model_dump(mode="json"),
        transform=transform,
        return_segment_map=True,
    )
    db.add(
        TranscriptAnnotation(
            transcript_id=transcript.id,
            version_id=version.id,
            segment_id=segment_map[target.id],
            author_id=principal.user.id,
            note=payload.note,
            is_unclear=payload.is_unclear,
        )
    )
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/operations:undo", response_model=TranscriptDetailResponse)
def undo_operation(
    transcript_id: uuid.UUID,
    payload: OperationCheckpointRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptDetailResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    operation = db.scalar(
        select(TranscriptEditOperation)
        .where(
            TranscriptEditOperation.transcript_id == transcript.id,
            TranscriptEditOperation.undone_at.is_(None),
        )
        .order_by(TranscriptEditOperation.created_at.desc())
    )
    if operation is None:
        raise HTTPException(status_code=409, detail="No edit operation can be undone")
    transcript.active_version_id = operation.from_version_id
    operation.undone_at = datetime.now(UTC)
    db.commit()
    return _detail_for_transcript(db, transcript)


@router.post("/{transcript_id}/operations:redo", response_model=TranscriptDetailResponse)
def redo_operation(
    transcript_id: uuid.UUID,
    payload: OperationCheckpointRequest,
    principal: TranscriptEditor,
    db: DbSession,
) -> TranscriptDetailResponse:
    transcript = _get_transcript(db, principal, transcript_id)
    _ensure_current_version(transcript, payload.base_version_id)
    operation = db.scalar(
        select(TranscriptEditOperation)
        .where(
            TranscriptEditOperation.transcript_id == transcript.id,
            TranscriptEditOperation.undone_at.is_not(None),
            TranscriptEditOperation.from_version_id == transcript.active_version_id,
        )
        .order_by(TranscriptEditOperation.undone_at.desc())
    )
    if operation is None:
        raise HTTPException(status_code=409, detail="No edit operation can be redone")
    transcript.active_version_id = operation.to_version_id
    operation.undone_at = None
    db.commit()
    return _detail_for_transcript(db, transcript)


def _get_transcript(db: Session, principal: Principal, transcript_id: uuid.UUID) -> Transcript:
    transcript = db.scalar(
        select(Transcript).where(
            Transcript.id == transcript_id, Transcript.organisation_id == principal.organisation.id
        )
    )
    if transcript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
    return transcript


def _active_version_id(transcript: Transcript) -> uuid.UUID:
    if transcript.active_version_id is None:
        raise HTTPException(status_code=409, detail="Transcript has no editable version")
    return transcript.active_version_id


def _ensure_current_version(transcript: Transcript, base_version_id: uuid.UUID | None) -> None:
    if base_version_id is not None and base_version_id != transcript.active_version_id:
        raise HTTPException(status_code=409, detail="Transcript version conflict")


def _source_segments(db: Session, version_id: uuid.UUID) -> list[TranscriptSegment]:
    return list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.version_id == version_id)
            .order_by(TranscriptSegment.sequence)
        )
    )


def _new_version(
    db: Session,
    transcript: Transcript,
    principal: Principal,
    source: str,
    change_summary: str,
) -> TranscriptVersion:
    previous_id = _active_version_id(transcript)
    next_version_number = (
        db.scalar(
            select(func.max(TranscriptVersion.version_number)).where(
                TranscriptVersion.transcript_id == transcript.id
            )
        )
        or 0
    ) + 1
    version = TranscriptVersion(
        transcript_id=transcript.id,
        version_number=next_version_number,
        parent_version_id=previous_id,
        created_by_id=principal.user.id,
        source=source,
        change_summary=change_summary,
    )
    db.add(version)
    db.flush()
    return version


def _create_version_from_segments(
    db: Session,
    transcript: Transcript,
    principal: Principal,
    source_segments: list[TranscriptSegment],
    *,
    operation_type: str,
    change_summary: str,
    payload: dict,
    transform: SegmentTransform,
    operation_segment_id: uuid.UUID | None = None,
    source: str = "human_edit",
    skip_segment_ids: set[uuid.UUID] | None = None,
    return_segment_map: bool = False,
):
    previous_id = _active_version_id(transcript)
    version = _new_version(db, transcript, principal, source, change_summary)
    skip_segment_ids = skip_segment_ids or set()
    segment_map: dict[uuid.UUID, uuid.UUID] = {}
    sequence = 1
    for source_segment in source_segments:
        if source_segment.id in skip_segment_ids:
            continue
        new_segment = _add_segment_copy(
            db,
            version.id,
            source_segment,
            sequence,
            transform(source_segment),
        )
        db.flush()
        segment_map[source_segment.id] = new_segment.id
        _copy_words(db, source_segment.id, new_segment.id)
        sequence += 1
    transcript.active_version_id = version.id
    _record_operation(
        db,
        transcript,
        principal,
        operation_type,
        from_version_id=previous_id,
        to_version_id=version.id,
        segment_id=operation_segment_id,
        payload=payload,
    )
    if return_segment_map:
        return version, segment_map
    return version


def _add_segment_copy(
    db: Session,
    version_id: uuid.UUID,
    source: TranscriptSegment,
    sequence: int,
    overrides: dict,
) -> TranscriptSegment:
    segment = TranscriptSegment(
        version_id=version_id,
        sequence=sequence,
        start_ms=overrides.get("start_ms", source.start_ms),
        end_ms=overrides.get("end_ms", source.end_ms),
        speaker_id=overrides.get("speaker_id", source.speaker_id),
        text=overrides.get("text", source.text),
        confidence=overrides.get("confidence", source.confidence),
        is_unclear=overrides.get("is_unclear", source.is_unclear),
        notes=overrides.get("notes", source.notes),
    )
    db.add(segment)
    return segment


def _copy_words(
    db: Session,
    source_segment_id: uuid.UUID,
    target_segment_id: uuid.UUID,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    query = (
        select(TranscriptWord)
        .where(TranscriptWord.segment_id == source_segment_id)
        .order_by(TranscriptWord.sequence)
    )
    words = list(db.scalars(query))
    sequence = 1
    for word in words:
        if start_ms is not None and word.end_ms <= start_ms:
            continue
        if end_ms is not None and word.start_ms >= end_ms:
            continue
        db.add(
            TranscriptWord(
                segment_id=target_segment_id,
                sequence=sequence,
                start_ms=word.start_ms,
                end_ms=word.end_ms,
                word=word.word,
                confidence=word.confidence,
            )
        )
        sequence += 1


def _record_operation(
    db: Session,
    transcript: Transcript,
    principal: Principal,
    operation_type: str,
    *,
    from_version_id: uuid.UUID,
    to_version_id: uuid.UUID,
    payload: dict,
    segment_id: uuid.UUID | None = None,
) -> TranscriptEditOperation:
    operation = TranscriptEditOperation(
        transcript_id=transcript.id,
        actor_id=principal.user.id,
        operation_type=operation_type,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
        segment_id=segment_id,
        payload=payload,
    )
    db.add(operation)
    return operation


def _validate_speaker(db: Session, transcript: Transcript, speaker_id: uuid.UUID | None) -> None:
    if speaker_id is None:
        return
    speaker = db.get(Speaker, speaker_id)
    if speaker is None or speaker.transcript_id != transcript.id:
        raise HTTPException(status_code=404, detail="Speaker not found")


def _segment_response(db: Session, segment: TranscriptSegment) -> TranscriptSegmentResponse:
    word_count = db.scalar(
        select(func.count(TranscriptWord.id)).where(TranscriptWord.segment_id == segment.id)
    )
    speaker = db.get(Speaker, segment.speaker_id) if segment.speaker_id else None
    return TranscriptSegmentResponse(
        id=segment.id,
        sequence=segment.sequence,
        start_ms=segment.start_ms,
        end_ms=segment.end_ms,
        text=segment.text,
        confidence=segment.confidence,
        is_unclear=segment.is_unclear,
        notes=segment.notes,
        speaker_id=segment.speaker_id,
        speaker_label=(speaker.display_name or speaker.label) if speaker else None,
        word_count=word_count or 0,
    )


def _detail_for_transcript(db: Session, transcript: Transcript) -> TranscriptDetailResponse:
    base = _response_for_transcript(db, transcript)
    if transcript.active_version_id is None:
        return TranscriptDetailResponse(**base.model_dump(), segments=[])
    segments = _source_segments(db, transcript.active_version_id)
    return TranscriptDetailResponse(
        **base.model_dump(),
        segments=[_segment_response(db, segment) for segment in segments],
    )


def _response_for_transcript(db: Session, transcript: Transcript) -> TranscriptResponse:
    version = (
        db.get(TranscriptVersion, transcript.active_version_id) if transcript.active_version_id else None
    )
    job = db.get(TranscriptionJob, transcript.job_id)
    asset_id = job.asset_id if job else None
    return TranscriptResponse(
        id=transcript.id,
        job_id=transcript.job_id,
        asset_id=asset_id,
        language=transcript.language,
        detected_language=transcript.detected_language,
        source_provider=transcript.source_provider,
        status=transcript.status,
        active_version=TranscriptVersionResponse.model_validate(version) if version else None,
        created_at=transcript.created_at,
    )
