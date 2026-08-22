import hashlib
import uuid
from datetime import UTC, datetime

import pytest

from app.public_config.contracts import (
    AdsTxtRecordInput,
    PublicConfigSnapshotInput,
    ads_txt_record_hash,
    public_config_observation_key,
)


def test_observation_and_record_keys_are_deterministic_and_scoped() -> None:
    tenant_id, site_id = uuid.uuid4(), uuid.uuid4()
    first = public_config_observation_key(
        tenant_id=tenant_id,
        site_id=site_id,
        config_type="ADS_TXT",
        fetch_kind="SCHEDULED",
        source_key="2026-08-21T12:00:00Z",
    )
    repeated = public_config_observation_key(
        tenant_id=tenant_id,
        site_id=site_id,
        config_type="ADS_TXT",
        fetch_kind="SCHEDULED",
        source_key=" 2026-08-21T12:00:00Z ",
    )
    other_site = public_config_observation_key(
        tenant_id=tenant_id,
        site_id=uuid.uuid4(),
        config_type="ADS_TXT",
        fetch_kind="SCHEDULED",
        source_key="2026-08-21T12:00:00Z",
    )

    assert first == repeated
    assert first != other_site
    assert len(first) == 64
    assert (
        ads_txt_record_hash(
            advertising_system_domain="example.com",
            publisher_account_id="account-1",
            relationship="DIRECT",
            cert_authority_id=None,
        )
        == hashlib.sha256(b"example.com\x1faccount-1\x1fDIRECT\x1f").hexdigest()
    )


def test_http_200_empty_ads_txt_cannot_be_marked_healthy() -> None:
    with pytest.raises(ValueError, match="without valid records"):
        PublicConfigSnapshotInput(
            observation_key="a" * 64,
            config_type="ADS_TXT",
            observed_at=datetime.now(UTC),
            http_status=200,
            content_hash="b" * 64,
            parse_status="VALID",
            normalizer_version="ads-txt-v1",
            summary={"valid_record_count": 0},
        )

    empty = PublicConfigSnapshotInput(
        observation_key="a" * 64,
        config_type="ADS_TXT",
        observed_at=datetime.now(UTC),
        http_status=200,
        content_hash="b" * 64,
        parse_status="EMPTY",
        normalizer_version="ads-txt-v1",
        summary={"valid_record_count": 0},
    )
    assert empty.parse_status == "EMPTY"


def test_validation_provenance_and_record_normalization_fail_closed() -> None:
    with pytest.raises(ValueError, match="require a primary"):
        PublicConfigSnapshotInput(
            observation_key="a" * 64,
            config_type="ROBOTS_TXT",
            observed_at=datetime.now(UTC),
            http_status=200,
            content_hash="b" * 64,
            parse_status="VALID",
            normalizer_version="robots-v1",
            fetch_kind="VALIDATION",
        )

    with pytest.raises(ValueError, match="normalized lowercase"):
        AdsTxtRecordInput(
            advertising_system_domain="Example.COM",
            publisher_account_id="account-1",
            relationship="DIRECT",
            cert_authority_id=None,
            record_hash="c" * 64,
        )
