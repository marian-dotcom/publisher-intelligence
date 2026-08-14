from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from app.connectors.core.contracts import ExtractPeriod
from app.connectors.gsc.client import GSCClient, GSCProviderError, _http_error
from app.connectors.gsc.definitions import GSC_SEARCH_DAILY_V1


class Transport:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.mark.parametrize(
    "property_id",
    ["sc-domain:example.com", "https://www.example.com/", "http://example.com/blog/"],
)
def test_property_identifier_is_preserved_exactly(property_id: str) -> None:
    assert GSCClient.canonical_property(property_id) == property_id


@pytest.mark.parametrize(
    "property_id", ["", "example.com", "sc-domain:", "https://example.com", "ftp://example.com/"]
)
def test_invalid_property_identifier_is_rejected(property_id: str) -> None:
    with pytest.raises(GSCProviderError):
        GSCClient.canonical_property(property_id)


async def test_sites_query_and_inspection_use_only_read_methods_and_encoded_property() -> None:
    transport = Transport([{"siteEntry": []}, {"rows": []}, {"inspectionResult": {}}])
    client = GSCClient(transport)
    definition = replace(GSC_SEARCH_DAILY_V1, row_limit=2, max_rows=4)

    await client.list_sites(access_token="fixture-token")
    await client.run_query(
        property_id="sc-domain:example.com",
        access_token="fixture-token",
        definition=definition,
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
    )
    await client.inspect_url(
        property_id="sc-domain:example.com",
        inspection_url="https://www.example.com/article/",
        access_token="fixture-token",
    )

    assert transport.calls[0]["method"] == "GET"
    assert transport.calls[0]["url"].endswith("/sites")
    assert "sc-domain%3Aexample.com" in transport.calls[1]["url"]
    assert transport.calls[1]["json_body"]["type"] == "web"
    assert transport.calls[1]["json_body"]["rowLimit"] == 2
    assert transport.calls[2]["url"].endswith("/urlInspection/index:inspect")
    assert set(transport.calls[2]["json_body"]) == {
        "inspectionUrl",
        "siteUrl",
        "languageCode",
    }
    assert "fixture-token" not in str(transport.calls[1]["json_body"])


async def test_pagination_stops_at_documented_daily_type_cap() -> None:
    row = {"keys": ["2026-08-12", "MOBILE"], "clicks": 1, "impressions": 1, "ctr": 1, "position": 1}
    transport = Transport(
        [
            {"rows": [row, row], "responseAggregationType": "byProperty"},
            {"rows": [row, row], "responseAggregationType": "byProperty"},
        ]
    )
    definition = replace(GSC_SEARCH_DAILY_V1, row_limit=2, max_rows=4)
    payload = await GSCClient(transport).run_query(
        property_id="sc-domain:example.com",
        access_token="fixture-token",
        definition=definition,
        period=ExtractPeriod(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert len(payload["rows"]) == 4
    assert payload["pagination"]["capReached"] is True
    assert [call["json_body"]["startRow"] for call in transport.calls] == [0, 2]


def test_inspection_url_must_belong_to_property() -> None:
    with pytest.raises(GSCProviderError) as raised:
        GSCClient.validate_inspection_url(
            "sc-domain:example.com", "https://attacker.example/article/"
        )
    assert raised.value.code == "INSPECTION_URL_OUTSIDE_PROPERTY"


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
def test_http_errors_are_sanitized(status: int, code: str, retryable: bool) -> None:
    error = _http_error(status)
    assert error.code == code
    assert error.retryable is retryable
    assert "token" not in str(error).lower()
