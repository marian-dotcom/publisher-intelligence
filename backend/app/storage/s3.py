import hashlib
from dataclasses import dataclass
from typing import Any

import boto3

from app.config.settings import Settings


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    sha256: str


class S3Storage:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._bucket = settings.s3_bucket
        self._client = client or boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id.get_secret_value(),
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            use_ssl=settings.s3_use_ssl,
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def bucket_exists(self) -> bool:
        self._client.head_bucket(Bucket=self._bucket)
        return True

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return StoredObject(key=key, size=len(content), sha256=digest)

    def head(self, *, key: str) -> dict[str, Any]:
        return dict(self._client.head_object(Bucket=self._bucket, Key=key))

    def get_bytes(self, *, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return bytes(response["Body"].read())

    def delete(self, *, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
