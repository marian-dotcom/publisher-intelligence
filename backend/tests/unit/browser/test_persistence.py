import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from app.browser.contracts import ArtifactContent, BrowserEvidence, BrowserTarget
from app.browser.persistence import EvidencePersister
from app.storage.s3 import StoredObject


class RecordingStorage:
    def __init__(self) -> None:
        self.keys: list[str] = []

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        del content_type
        self.keys.append(key)
        return StoredObject(
            key=key,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )


class RecordingRepository:
    def __init__(self) -> None:
        self.finalized: dict[str, Any] | None = None

    async def finalize(self, **kwargs: Any) -> None:
        self.finalized = kwargs

    async def previous_comparable_selection(self, **kwargs: Any) -> None:
        del kwargs
        return None


async def test_manifest_is_uploaded_last_and_finalized_after_objects() -> None:
    ids = [uuid.uuid4() for _ in range(5)]
    target = BrowserTarget(
        checkpoint_run_id=ids[0],
        tenant_id=ids[1],
        site_id=ids[2],
        monitored_url_id=ids[3],
        scenario_id=ids[4],
        url="https://example.com/?secret=not-in-manifest",
        canonical_domain="example.com",
        scenario_code="core_desktop_v1",
        scenario_version=1,
        locale="en-US",
        timezone="UTC",
        viewport_width=1440,
        viewport_height=900,
    )
    now = datetime.now(UTC)
    evidence = BrowserEvidence(
        status="COMPLETE",
        started_at=now,
        completed_at=now,
        final_url="https://example.com/",
        http_status=200,
        playwright_version="test",
        chromium_version="test",
        environment={"synthetic": True},
        artifacts=[
            ArtifactContent(
                artifact_type="RAW_DOM",
                filename="dom/raw.html",
                content_type="text/html",
                retention_class="RAW_MEDIUM",
                content=b"<html></html>",
            )
        ],
    )
    repository = RecordingRepository()
    storage = RecordingStorage()
    persister = EvidencePersister(repository, storage)  # type: ignore[arg-type]

    manifest = await persister.persist(target=target, attempt_number=1, evidence=evidence)

    assert storage.keys[-1].endswith("/manifest.json")
    assert repository.finalized is not None
    assert [item.artifact_type for item in repository.finalized["artifacts"]] == [
        "RAW_DOM",
        "MANIFEST",
    ]
    assert manifest["schema"] == "browser-checkpoint-manifest/v3"
    assert manifest["comparison"]["status"] == "NOT_COMPARABLE"
    assert "secret" not in str(manifest)
