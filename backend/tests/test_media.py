from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from app.services.media import validate_upload
from app.storage.local import LocalFilesystemStorage, StorageLimitExceededError


def test_accepts_wav_with_matching_signature() -> None:
    upload = UploadFile(filename="meeting.wav", file=BytesIO(b"RIFF\x00\x00\x00\x00WAVEfmt "))

    validated = validate_upload(upload)

    assert validated.filename == "meeting.wav"
    assert validated.content_type == "audio/wav"


def test_rejects_mislabeled_media() -> None:
    upload = UploadFile(filename="meeting.mp3", file=BytesIO(b"not an mp3"))

    with pytest.raises(HTTPException, match="signature"):
        validate_upload(upload)


def test_local_storage_hashes_and_limits_uploads(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(tmp_path)
    stored = storage.save(BytesIO(b"safe audio"), "org/assets/file.wav", max_bytes=100)

    assert stored.byte_size == 10
    assert storage.open(stored.storage_key).read() == b"safe audio"

    with pytest.raises(StorageLimitExceededError):
        storage.save(BytesIO(b"x" * 101), "org/assets/too-large.wav", max_bytes=100)
