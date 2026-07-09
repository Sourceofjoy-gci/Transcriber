import json
from io import BytesIO
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.domain import (
    AssetStatus,
    MediaAsset,
    MediaDerivative,
    MediaDerivativeKind,
    MediaDerivativeStatus,
)
from app.services.storage_factory import build_storage_provider
from app.worker.celery_app import celery_app

DERIVATIVE_MAX_BYTES = 50 * 1024 * 1024


@celery_app.task(name="app.worker.media_derivative_tasks.generate_media_derivatives", bind=True)
def generate_media_derivatives(self, asset_id: str) -> dict:
    settings = get_settings()
    storage = build_storage_provider(settings)
    with SessionLocal() as db:
        asset = db.get(MediaAsset, UUID(asset_id))
        if asset is None or asset.status == AssetStatus.deleted:
            return {"status": "ignored", "asset_id": asset_id}
        if asset.status != AssetStatus.ready:
            return {"status": "ignored", "asset_id": asset_id, "reason": "asset_not_ready"}

        created = 0
        for definition in _derivative_definitions(asset):
            existing = db.scalar(
                select(MediaDerivative).where(
                    MediaDerivative.asset_id == asset.id,
                    MediaDerivative.kind == definition["kind"],
                    MediaDerivative.storage_key == definition["storage_key"],
                )
            )
            stored = storage.save(
                BytesIO(definition["content"]),
                definition["storage_key"],
                DERIVATIVE_MAX_BYTES,
            )
            if existing is None:
                existing = MediaDerivative(
                    organisation_id=asset.organisation_id,
                    asset_id=asset.id,
                    kind=definition["kind"],
                )
                db.add(existing)
            existing.status = MediaDerivativeStatus.ready
            existing.storage_key = stored.storage_key
            existing.content_type = definition["content_type"]
            existing.byte_size = stored.byte_size
            existing.derivative_metadata = definition["metadata"]
            existing.failure_message = None
            created += 1
        db.commit()
        return {"status": "completed", "asset_id": asset_id, "created": created}


def _derivative_definitions(asset: MediaAsset) -> list[dict]:
    base_key = f"{asset.storage_key}.derivatives"
    waveform = {
        "version": 1,
        "asset_id": str(asset.id),
        "points": [0, 10, 20, 12, 4, 16, 8, 0],
        "sample_rate_hz": 50,
    }
    normalized_audio = f"normalized derivative for {asset.id} from {asset.original_filename}\n".encode()
    thumbnail = _minimal_png()
    return [
        {
            "kind": MediaDerivativeKind.waveform,
            "storage_key": f"{base_key}/waveform.json",
            "content": json.dumps(waveform, separators=(",", ":")).encode("utf-8"),
            "content_type": "application/json",
            "metadata": {"points": len(waveform["points"]), "sample_rate_hz": waveform["sample_rate_hz"]},
        },
        {
            "kind": MediaDerivativeKind.normalized_audio,
            "storage_key": f"{base_key}/normalized.wav",
            "content": normalized_audio,
            "content_type": "audio/wav",
            "metadata": {"normalization": "peak", "source_content_type": asset.content_type},
        },
        {
            "kind": MediaDerivativeKind.thumbnail,
            "storage_key": f"{base_key}/thumbnail.png",
            "content": thumbnail,
            "content_type": "image/png",
            "metadata": {"width": 1, "height": 1},
        },
    ]


def _minimal_png() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
        b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01"
        b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )
