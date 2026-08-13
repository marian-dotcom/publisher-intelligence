import uuid

import pytest

from app.config.settings import get_settings
from app.storage.s3 import S3Storage

pytestmark = pytest.mark.integration


def test_minio_round_trip() -> None:
    storage = S3Storage(get_settings())
    key = f"integration/{uuid.uuid4()}.txt"
    content = b"publisher evidence boundary"

    stored = storage.put_bytes(key=key, content=content, content_type="text/plain")
    try:
        assert storage.bucket_exists()
        assert storage.get_bytes(key=key) == content
        assert storage.head(key=key)["Metadata"]["sha256"] == stored.sha256
    finally:
        storage.delete(key=key)
