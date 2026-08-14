from collections.abc import Mapping
from datetime import date
from typing import Any

import pytest

from app.connectors.core.contracts import ExtractPeriod
from app.connectors.ga4.client import GA4Client, GA4ProviderError, _http_error
from app.connectors.ga4.definitions import GA4_TRAFFIC_HOURLY_V1


class RecordingTransport:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        return self.response


async def test_client_uses_only_metadata_get_and_bounded_report_post() -> None:
    transport = RecordingTransport({"ok": True})
    client = GA4Client(transport)

    await client.get_metadata(property_id="123456", access_token="secret-token")
    await client.run_report(
        property_id="123456",
        access_token="secret-token",
        definition=GA4_TRAFFIC_HOURLY_V1,
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 13)),
    )

    assert transport.calls[0] == {
        "method": "GET",
        "url": "https://analyticsdata.googleapis.com/v1beta/properties/123456/metadata",
        "access_token": "secret-token",
    }
    report = transport.calls[1]
    assert report["method"] == "POST"
    assert report["url"].endswith("/properties/123456:runReport")
    assert report["json_body"] == {
        "dimensions": [
            {"name": "dateHour"},
            {"name": "deviceCategory"},
            {"name": "sessionDefaultChannelGroup"},
        ],
        "metrics": [
            {"name": "activeUsers"},
            {"name": "sessions"},
            {"name": "screenPageViews"},
            {"name": "engagedSessions"},
        ],
        "dateRanges": [{"startDate": "2026-08-12", "endDate": "2026-08-13"}],
        "keepEmptyRows": False,
        "returnPropertyQuota": True,
    }
    assert "secret-token" not in str(report["json_body"])


@pytest.mark.parametrize("property_id", ["", "properties/123", "abc", "-1", "0"])
def test_property_id_must_be_a_positive_numeric_id(property_id: str) -> None:
    with pytest.raises(GA4ProviderError, match="numeric"):
        GA4Client.property_resource(property_id)


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "AUTH_EXPIRED", False),
        (403, "PERMISSION_ERROR", False),
        (429, "QUOTA_LIMIT", True),
        (500, "PROVIDER_ERROR", True),
        (400, "INVALID_QUERY", False),
    ],
)
def test_http_failures_are_sanitized_and_classified(
    status: int, code: str, retryable: bool
) -> None:
    error = _http_error(status)
    assert error.code == code
    assert error.retryable is retryable
    assert "token" not in str(error).lower()
