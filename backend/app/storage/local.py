from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.storage.contracts import SignedStorageUrl, StoredObject


class StorageLimitExceededError(Exception):
    pass


class LocalFilesystemStorage:
    key = "local_filesystem"

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._staging_directory = self.root / ".staging"
        self._staging_directory.mkdir(exist_ok=True)

    def save(self, source: BinaryIO, object_key: str, max_bytes: int) -> StoredObject:
        destination = self._resolve(object_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._staging_directory / f"{uuid4().hex}.upload"
        digest = sha256()
        byte_size = 0
        try:
            with temporary_path.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    byte_size += len(chunk)
                    if byte_size > max_bytes:
                        raise StorageLimitExceededError(
                            f"Upload exceeds configured limit of {max_bytes} bytes"
                        )
                    digest.update(chunk)
                    target.write(chunk)
            temporary_path.replace(destination)
            return StoredObject(storage_key=object_key, byte_size=byte_size, sha256=digest.hexdigest())
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def open(self, object_key: str) -> BinaryIO:
        return self._resolve(object_key).open("rb")

    def path_for(self, object_key: str) -> str:
        return str(self._resolve(object_key))

    def delete(self, object_key: str) -> None:
        self._resolve(object_key).unlink(missing_ok=True)

    def signed_url(
        self, object_key: str, expires_in_seconds: int, filename: str | None = None
    ) -> SignedStorageUrl:
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in_seconds)
        return SignedStorageUrl(url=self.path_for(object_key), expires_at=expires_at, headers={})

    def _resolve(self, object_key: str) -> Path:
        candidate = (self.root / object_key).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError("Storage key resolves outside configured root")
        return candidate
