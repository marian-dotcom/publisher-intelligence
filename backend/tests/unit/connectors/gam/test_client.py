import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest

from app.connectors.gam.client import GAMClient, GAMProviderError

FIXTURES = Path(__file__).parents[3] / "fixtures" / "connectors" / "gam"


def load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


async def no_sleep(_: float) -> None:
    return None


class Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.repeat_token = False

    async def request(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        url = kwargs["url"]
        if url.endswith(":run"):
            return {
                "name": "networks/1234567/operations/reports/101/runs/run-1",
                "done": False,
            }
        if "/operations/" in url:
            return {
                "name": "networks/1234567/operations/reports/101/runs/run-1",
                "done": True,
                "response": {"reportResult": "networks/1234567/reports/101/results/result-1"},
            }
        query = kwargs.get("query") or {}
        if query.get("pageToken"):
            page = load("inventory_rows_page_2.json")
            if self.repeat_token:
                page["nextPageToken"] = "sanitized-page-2"
            return page
        return load("inventory_rows_page_1.json")


async def test_async_report_polls_and_fetches_every_page() -> None:
    transport = Transport()
    client = GAMClient(transport, sleep=no_sleep, initial_poll_seconds=0)
    payload = await client.run_report(
        network_code="1234567",
        report_resource="networks/1234567/reports/101",
        access_token="fixture-token",
    )
    assert len(payload["rows"]) == 2
    assert payload["pagination"] == {
        "pagesFetched": 2,
        "pageSize": 10000,
        "totalRowCount": 2,
        "allPagesFetched": True,
    }
    assert [call["method"] for call in transport.calls] == ["POST", "GET", "GET", "GET"]


async def test_repeated_page_token_is_not_treated_as_complete() -> None:
    transport = Transport()
    transport.repeat_token = True
    client = GAMClient(transport, sleep=no_sleep, initial_poll_seconds=0)
    with pytest.raises(GAMProviderError) as raised:
        await client.run_report(
            network_code="1234567",
            report_resource="networks/1234567/reports/101",
            access_token="fixture-token",
        )
    assert raised.value.code == "INVALID_RESPONSE"


def test_report_binding_cannot_cross_network() -> None:
    with pytest.raises(GAMProviderError) as raised:
        GAMClient.canonical_report_resource("1234567", "networks/7654321/reports/101")
    assert raised.value.code == "REPORT_BINDING_INVALID"
