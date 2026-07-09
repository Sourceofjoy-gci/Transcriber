from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Protocol


@dataclass(frozen=True)
class StoredObject:
    storage_key: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class SignedStorageUrl:
    url: str
    expires_at: datetime
    method: str = "GET"
    headers: dict[str, str] | None = None


class StorageProvider(Protocol):
    key: str

    def save(self, source: BinaryIO, object_key: str, max_bytes: int) -> StoredObject: ...

    def open(self, object_key: str) -> BinaryIO: ...

    def path_for(self, object_key: str) -> str: ...

    def delete(self, object_key: str) -> None: ...

    def signed_url(
        self, object_key: str, expires_in_seconds: int, filename: str | None = None
    ) -> SignedStorageUrl: ...
