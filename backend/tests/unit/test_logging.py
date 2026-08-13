from app.common.logging import redact


def test_redact_removes_nested_sensitive_values() -> None:
    payload = {
        "job_id": "job-1",
        "payload": {
            "connection_id": "connection-1",
            "refresh_token": "secret-token",
        },
        "authorization": "Bearer secret",
    }

    result = redact(payload)

    assert result["job_id"] == "job-1"
    assert result["payload"]["connection_id"] == "connection-1"
    assert result["payload"]["refresh_token"] == "[REDACTED]"
    assert result["authorization"] == "[REDACTED]"
    assert "secret-token" not in str(result)
