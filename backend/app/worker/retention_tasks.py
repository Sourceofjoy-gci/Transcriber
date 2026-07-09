from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.domain import AssetStatus, MediaAsset, MediaDerivative, Organisation, Project
from app.services.storage_factory import build_storage_provider
from app.worker.celery_app import celery_app

DEFAULT_RETENTION_DAYS = 30


@celery_app.task(name="app.worker.retention_tasks.purge_expired_assets", bind=True)
def purge_expired_assets(self) -> dict:
    settings = get_settings()
    storage = build_storage_provider(settings)
    now = datetime.now(UTC)
    purged_assets = 0
    deleted_objects = 0

    with SessionLocal() as db:
        assets = list(
            db.scalars(
                select(MediaAsset)
                .where(MediaAsset.status == AssetStatus.deleted, MediaAsset.deleted_at.is_not(None))
                .order_by(MediaAsset.deleted_at)
            )
        )
        for asset in assets:
            if _is_under_legal_hold(asset, now):
                continue
            if not _retention_expired(db, asset, now):
                continue

            derivatives = list(
                db.scalars(select(MediaDerivative).where(MediaDerivative.asset_id == asset.id))
            )
            for derivative in derivatives:
                if derivative.storage_key:
                    storage.delete(derivative.storage_key)
                    deleted_objects += 1
                db.delete(derivative)
            storage.delete(asset.storage_key)
            deleted_objects += 1
            db.delete(asset)
            purged_assets += 1
        db.commit()

    return {
        "status": "completed",
        "purged_assets": purged_assets,
        "deleted_objects": deleted_objects,
    }


def _is_under_legal_hold(asset: MediaAsset, now: datetime) -> bool:
    legal_hold_until = _ensure_aware(asset.legal_hold_until)
    return legal_hold_until is not None and legal_hold_until > now


def _retention_expired(db, asset: MediaAsset, now: datetime) -> bool:
    deleted_at = _ensure_aware(asset.deleted_at)
    if deleted_at is None:
        return False
    retention_days = _effective_retention_days(db, asset)
    return deleted_at + timedelta(days=retention_days) <= now


def _effective_retention_days(db, asset: MediaAsset) -> int:
    if asset.project_id is not None:
        project = db.get(Project, asset.project_id)
        if project and project.retention_days:
            return project.retention_days
    organisation = db.get(Organisation, asset.organisation_id)
    if organisation and organisation.retention_days:
        return organisation.retention_days
    return DEFAULT_RETENTION_DAYS


def _ensure_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
