from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from typing import BinaryIO
from urllib.parse import quote

from app.storage.contracts import SignedStorageUrl, StoredObject
from app.storage.local import StorageLimitExceededError


class S3CompatibleStorage:
    key = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key_id: str | None,
        secret_access_key: str | None,
        region_name: str | None,
        use_ssl: bool = True,
    ) -> None:
        if not bucket:
            raise RuntimeError("S3 storage requires a bucket name")
        try:
            import boto3
        except ImportError as error:
            raise RuntimeError("S3 storage requires the optional boto3 dependency") from error

        if endpoint_url is None:
            endpoint_url = None
        elif not endpoint_url.startswith(("http://", "https://")):
            scheme = "https" if use_ssl else "http"
            endpoint_url = f"{scheme}://{endpoint_url}"

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
            use_ssl=use_ssl,
        )

    def save(self, source: BinaryIO, object_key: str, max_bytes: int) -> StoredObject:
        digest = sha256()
        byte_size = 0
        buffer = BytesIO()
        while chunk := source.read(1024 * 1024):
            byte_size += len(chunk)
            if byte_size > max_bytes:
                raise StorageLimitExceededError(f"Object exceeds configured limit of {max_bytes} bytes")
            digest.update(chunk)
            buffer.write(chunk)
        buffer.seek(0)
        self.client.upload_fileobj(buffer, self.bucket, object_key)
        return StoredObject(storage_key=object_key, byte_size=byte_size, sha256=digest.hexdigest())

    def open(self, object_key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        return BytesIO(response["Body"].read())

    def path_for(self, object_key: str) -> str:
        raise RuntimeError("S3-compatible storage does not expose local filesystem paths")

    def delete(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def signed_url(
        self, object_key: str, expires_in_seconds: int, filename: str | None = None
    ) -> SignedStorageUrl:
        params: dict[str, str] = {"Bucket": self.bucket, "Key": object_key}
        if filename:
            params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
        url = self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in_seconds,
            HttpMethod="GET",
        )
        return SignedStorageUrl(
            url=url,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
            headers={},
        )
