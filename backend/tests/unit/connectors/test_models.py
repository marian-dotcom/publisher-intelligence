import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import insert

from app.connectors.core.persistence import _series_key
from app.connectors.models import DataConnection, MetricPoint


def test_connection_insert_uses_mapped_metadata_attribute_not_declarative_metadata() -> None:
    statement = insert(DataConnection).values(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        provider="GA4",
        external_property_id="123456",
        status="PENDING",
        scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        secret_reference="env:GA4_TEST_ACCESS_TOKEN",
        connection_metadata={},
    )

    compiled = str(statement)
    assert "metadata" in compiled
    assert "connection_metadata" not in compiled


def test_source_time_can_preserve_gsc_offset_hour() -> None:
    source_time_type = MetricPoint.__table__.c.source_time.type
    assert isinstance(source_time_type, String)
    assert source_time_type.length == 64


def test_series_identity_includes_provider() -> None:
    tenant_id = uuid.uuid4()
    site_id = uuid.uuid4()
    ga4_key = _series_key(
        tenant_id=tenant_id,
        site_id=site_id,
        metric_code="shared.code",
        semantics_version="v1",
        granularity="DAY",
        dimensions={"device": "MOBILE"},
        source="GA4",
    )
    gsc_key = _series_key(
        tenant_id=tenant_id,
        site_id=site_id,
        metric_code="shared.code",
        semantics_version="v1",
        granularity="DAY",
        dimensions={"device": "MOBILE"},
        source="GSC",
    )
    assert ga4_key != gsc_key
