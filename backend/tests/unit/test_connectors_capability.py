from pathlib import Path

from app.connectors.models import DataConnection

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0022_monetization_capability.py"
).read_text()


def test_migration_0022_defines_capability_vocabulary() -> None:
    assert "monetization_capability" in MIGRATION
    for value in ("ABSOLUTE", "RELATIVE_ONLY", "UNKNOWN"):
        assert f"'{value}'" in MIGRATION
    assert "ck_data_connections_monetization_capability" in MIGRATION


def test_model_mirrors_capability_column() -> None:
    column = DataConnection.__table__.c["monetization_capability"]
    assert column.nullable is False
    assert "UNKNOWN" in str(column.server_default.arg)
