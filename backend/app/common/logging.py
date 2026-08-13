import json
import logging
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "cookie",
    "database_url",
    "password",
    "refresh_token",
    "secret",
    "secret_access_key",
    "session_id",
    "signed_url",
    "token",
}


def redact(value: Any, key: str | None = None) -> Any:
    if key is not None and any(marker in key.lower() for marker in SENSITIVE_KEYS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, Mapping):
            payload.update(redact(context))
        return json.dumps(payload, sort_keys=True, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
