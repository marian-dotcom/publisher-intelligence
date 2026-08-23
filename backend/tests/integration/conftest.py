"""Shared isolation fixture for PostgreSQL-backed integration tests.

Autouse: every integration test starts from a predictable database state,
independent of test-file ordering. The purge targets only the configured
integration database (DATABASE_URL); production databases are never touched
because application settings resolve that URL exclusively from environment
configuration.
"""
import asyncio

import pytest

from app.db.session import get_session_factory
from tests.integration.purge import make_purge


@pytest.fixture(autouse=True)
def clean_integration_database() -> None:
    factory = get_session_factory()
    purge = make_purge(factory)
    asyncio.run(purge())
