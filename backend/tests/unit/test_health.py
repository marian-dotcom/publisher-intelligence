from fastapi.testclient import TestClient

from app.api.health import database_ready, object_storage_ready
from app.main import app


async def dependency_up() -> bool:
    return True


async def dependency_down() -> bool:
    return False


def test_liveness_does_not_require_dependencies() -> None:
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_only_dependency_state() -> None:
    app.dependency_overrides[database_ready] = dependency_up
    app.dependency_overrides[object_storage_ready] = dependency_down
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "status": "not_ready",
            "dependencies": {"database": True, "object_storage": False},
        }
    }
    assert "postgresql" not in response.text.lower()
    assert "secret" not in response.text.lower()
