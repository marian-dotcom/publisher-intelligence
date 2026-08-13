from io import BytesIO
from typing import Any

from app.config.settings import Settings
from app.storage.s3 import S3Storage


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def head_bucket(self, **kwargs: Any) -> dict[str, Any]:
        return {"Bucket": kwargs["Bucket"]}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects[kwargs["Key"]] = kwargs["Body"]
        return {}

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"ContentLength": len(self.objects[kwargs["Key"]])}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        return {"Body": BytesIO(self.objects[kwargs["Key"]])}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects.pop(kwargs["Key"], None)
        return {}


def test_storage_round_trip_and_hash() -> None:
    client = FakeS3Client()
    storage = S3Storage(Settings(), client=client)

    stored = storage.put_bytes(
        key="tests/evidence.txt", content=b"evidence", content_type="text/plain"
    )

    assert stored.size == 8
    assert stored.sha256 == "ee8250fb76e094b34b471f13a73dbbe51d1ae142e9df59d7c0d31ec20f0a0a8e"
    assert storage.head(key=stored.key)["ContentLength"] == 8
    assert storage.get_bytes(key=stored.key) == b"evidence"
    storage.delete(key=stored.key)
    assert stored.key not in client.objects
