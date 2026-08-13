import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.integration


def test_readiness_with_real_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"database": True, "object_storage": True},
    }
