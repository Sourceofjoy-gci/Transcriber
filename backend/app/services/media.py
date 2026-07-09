import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import PurePath
from urllib.parse import urlencode

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.domain import AssetStatus, MediaAsset, MediaDerivative, MediaMetadata, Organisation, Project
from app.services.authorization import Principal
from app.services.malware import MalwareScanner
from app.storage.contracts import SignedStorageUrl, StorageProvider
from app.storage.local import LocalFilesystemStorage, StorageLimitExceededError

MEDIA_TYPES = {
    ".aac": "audio/aac",
    ".avi": "video/x-msvideo",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mov": "video/quicktime",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".webm": "video/webm",
}


@dataclass(frozen=True)
class ValidatedMedia:
    filename: str
    extension: str
    content_type: str


def validate_upload(file: UploadFile) -> ValidatedMedia:
    filename = _sanitize_filename(file.filename)
    extension = PurePath(filename).suffix.lower()
    if extension not in MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media file type"
        )
    header = file.file.read(64)
    file.file.seek(0)
    if not _matches_signature(extension, header):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Media signature does not match file type",
        )
    return ValidatedMedia(filename=filename, extension=extension, content_type=MEDIA_TYPES[extension])


class MediaService:
    def __init__(
        self, db: Session, storage: StorageProvider, settings: Settings, scanner: MalwareScanner
    ) -> None:
        self.db = db
        self.storage = storage
        self.settings = settings
        self.scanner = scanner

    def upload(self, principal: Principal, file: UploadFile, project_id: uuid.UUID | None) -> MediaAsset:
        validated = validate_upload(file)
        if project_id:
            project = self.db.scalar(
                select(Project).where(
                    Project.id == project_id, Project.organisation_id == principal.organisation.id
                )
            )
            if project is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        asset_id = uuid.uuid4()
        storage_key = self._asset_storage_key(principal.organisation.id, asset_id, validated.extension)
        try:
            stored = self.storage.save(file.file, storage_key, self.settings.max_upload_bytes)
        except StorageLimitExceededError as error:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(error)
            ) from error
        scan_result = self.scanner.scan(self.storage.path_for(stored.storage_key))
        if not scan_result.clean:
            self.storage.delete(stored.storage_key)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=scan_result.message or "Media scanning failed",
            )

        asset = MediaAsset(
            id=asset_id,
            organisation_id=principal.organisation.id,
            project_id=project_id,
            uploaded_by_id=principal.user.id,
            original_filename=validated.filename,
            content_type=validated.content_type,
            byte_size=stored.byte_size,
            sha256=stored.sha256,
            storage_key=stored.storage_key,
            status=AssetStatus.uploaded,
        )
        self.db.add(asset)
        self.db.flush()
        return asset

    def get_asset(self, principal: Principal, asset_id: uuid.UUID) -> MediaAsset:
        asset = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.id == asset_id,
                MediaAsset.organisation_id == principal.organisation.id,
                MediaAsset.deleted_at.is_(None),
            )
        )
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
        return asset

    def get_metadata(self, asset_id: uuid.UUID) -> MediaMetadata | None:
        return self.db.scalar(select(MediaMetadata).where(MediaMetadata.asset_id == asset_id))

    def list_derivatives(self, principal: Principal, asset_id: uuid.UUID) -> list[MediaDerivative]:
        asset = self.get_asset(principal, asset_id)
        return list(
            self.db.scalars(
                select(MediaDerivative)
                .where(
                    MediaDerivative.asset_id == asset.id,
                    MediaDerivative.organisation_id == principal.organisation.id,
                )
                .order_by(MediaDerivative.kind, MediaDerivative.created_at)
            )
        )

    def signed_download_url(
        self,
        asset: MediaAsset,
        *,
        api_download_url: str,
        expires_in_seconds: int = 300,
    ) -> SignedStorageUrl:
        if self.storage.key != LocalFilesystemStorage.key:
            return self.storage.signed_url(
                asset.storage_key,
                expires_in_seconds,
                filename=asset.original_filename,
            )
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        separator = "&" if "?" in api_download_url else "?"
        query = urlencode({"expires_at": expires_at.isoformat()})
        return SignedStorageUrl(
            url=f"{api_download_url}{separator}{query}",
            expires_at=expires_at,
            headers={},
        )

    def storage_overview(self, principal: Principal) -> dict:
        original_bytes = (
            self.db.scalar(
                select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
                    MediaAsset.organisation_id == principal.organisation.id,
                    MediaAsset.status != AssetStatus.deleted,
                )
            )
            or 0
        )
        derivative_bytes = (
            self.db.scalar(
                select(func.coalesce(func.sum(MediaDerivative.byte_size), 0)).where(
                    MediaDerivative.organisation_id == principal.organisation.id
                )
            )
            or 0
        )
        active_assets = (
            self.db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(
                    MediaAsset.organisation_id == principal.organisation.id,
                    MediaAsset.status != AssetStatus.deleted,
                )
            )
            or 0
        )
        deleted_assets = (
            self.db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(
                    MediaAsset.organisation_id == principal.organisation.id,
                    MediaAsset.status == AssetStatus.deleted,
                )
            )
            or 0
        )
        now = datetime.now(UTC)
        legal_hold_assets = (
            self.db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(
                    MediaAsset.organisation_id == principal.organisation.id,
                    MediaAsset.legal_hold_until.is_not(None),
                    MediaAsset.legal_hold_until > now,
                )
            )
            or 0
        )
        organisation = self.db.get(Organisation, principal.organisation.id)
        return {
            "provider": self.storage.key,
            "healthy": True,
            "storage_bytes": int(original_bytes) + int(derivative_bytes),
            "original_bytes": int(original_bytes),
            "derivative_bytes": int(derivative_bytes),
            "active_assets": int(active_assets),
            "deleted_assets": int(deleted_assets),
            "legal_hold_assets": int(legal_hold_assets),
            "retention_days": organisation.retention_days if organisation else None,
        }

    @staticmethod
    def _asset_storage_key(organisation_id: uuid.UUID, asset_id: uuid.UUID, extension: str) -> str:
        day = datetime.now(UTC).strftime("%Y/%m/%d")
        return f"organisations/{organisation_id}/assets/{day}/{asset_id}/original{extension}"


def _sanitize_filename(value: str | None) -> str:
    filename = PurePath(value or "upload").name
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename).strip()
    if not filename or filename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="A valid filename is required"
        )
    return filename[:500]


def _matches_signature(extension: str, header: bytes) -> bool:
    if extension == ".mp3":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
        )
    if extension == ".wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if extension in {".m4a", ".mp4", ".mov"}:
        return header[4:8] == b"ftyp"
    if extension == ".avi":
        return header.startswith(b"RIFF") and header[8:12] == b"AVI "
    if extension == ".webm":
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if extension == ".ogg":
        return header.startswith(b"OggS")
    if extension == ".flac":
        return header.startswith(b"fLaC")
    if extension == ".aac":
        return len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0
    return False
