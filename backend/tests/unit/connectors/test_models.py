import uuid

from sqlalchemy.dialects.postgresql import insert

from app.connectors.models import DataConnection


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
