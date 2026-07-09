from app.core.config import Settings
from app.storage.contracts import StorageProvider
from app.storage.local import LocalFilesystemStorage
from app.storage.s3 import S3CompatibleStorage


def build_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_provider == LocalFilesystemStorage.key:
        return LocalFilesystemStorage(settings.storage_root)
    if settings.storage_provider in {S3CompatibleStorage.key, "s3_compatible", "minio"}:
        return S3CompatibleStorage(
            bucket=settings.s3_bucket or "",
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
        )
    raise RuntimeError(f"Unsupported storage provider: {settings.storage_provider}")
