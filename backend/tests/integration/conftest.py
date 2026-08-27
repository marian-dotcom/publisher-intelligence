"""Shared isolation fixtures for PostgreSQL-backed integration tests.

Autouse: every integration test starts from a predictable database state
and a clean rate-limit store, independent of test-file ordering.
"""

import asyncio

import pytest

from app.auth.rate_limit import get_rate_limit_store
from app.db.session import get_session_factory
from tests.integration.purge import make_purge


@pytest.fixture(autouse=True)
def clean_integration_database() -> None:
    purge = make_purge(get_session_factory)
    asyncio.run(purge())


@pytest.fixture(autouse=True)
def _clear_rate_limit_store() -> None:
    """Reset the in-memory rate limiter before every integration test.

    Prevents cross-test counter accumulation when the rate limiter is active.
    """
    get_rate_limit_store()._counts.clear()
