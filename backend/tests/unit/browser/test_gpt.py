import uuid

from app.browser.contracts import ExpectedGPTSlot
from app.browser.gpt import gpt_stable_key, parse_gpt_snapshot


def test_stable_key_prefers_ad_unit_path_and_falls_back_to_dom() -> None:
    assert gpt_stable_key("/123/article/top", "top-slot") == "gpt|ad-unit|/123/article/top"
    assert gpt_stable_key(None, "top-slot") == "gpt|dom|top-slot"
    assert gpt_stable_key(None, None) is None


def test_snapshot_preserves_independent_lifecycle_stages_and_refresh_count() -> None:
    raw = {
        "present": True,
        "observable": True,
        "version": "test-1",
        "slots": [
            {
                "adUnitPath": "/123/article/top",
                "domElementId": "top-slot",
                "sizes": ["300x250", "fluid", "300x250"],
                "definedAtMs": 1,
                "requestedAtMs": 10,
                "responseAtMs": 20,
                "renderEndedAtMs": 30,
                "onloadAtMs": None,
                "viewableAtMs": 50,
                "isEmpty": False,
                "creativeId": "creative-1",
                "lineItemId": "line-1",
                "requestCount": 2,
            }
        ],
    }

    present, observable, version, slots, errors = parse_gpt_snapshot(raw, ())

    assert present and observable
    assert version == "test-1"
    assert errors == []
    assert len(slots) == 1
    slot = slots[0]
    assert slot.sizes == ("300x250", "fluid")
    assert slot.request_count == 2
    assert slot.render_ended_at_ms == 30
    assert slot.onload_at_ms is None
    assert slot.viewable_at_ms == 50


def test_snapshot_merges_expected_and_keeps_absent_stages_null() -> None:
    expected_path = "/123/article/top"
    missing_path = "/123/article/missing"
    expected = (
        ExpectedGPTSlot(
            entity_id=uuid.uuid4(),
            stable_key=gpt_stable_key(expected_path, None) or "",
            ad_unit_path=expected_path,
            sizes=("300x250",),
        ),
        ExpectedGPTSlot(
            entity_id=uuid.uuid4(),
            stable_key=gpt_stable_key(missing_path, None) or "",
            ad_unit_path=missing_path,
            sizes=("728x90",),
        ),
    )
    raw = {
        "present": True,
        "observable": True,
        "slots": [{"adUnitPath": expected_path, "definedAtMs": 3, "requestCount": 0}],
    }

    _, _, _, slots, _ = parse_gpt_snapshot(raw, expected)

    by_path = {slot.ad_unit_path: slot for slot in slots}
    assert by_path[expected_path].expected is True
    assert by_path[expected_path].present is True
    missing = by_path[missing_path]
    assert missing.expected is True
    assert missing.present is False
    assert missing.defined_at_ms is None
    assert missing.requested_at_ms is None
    assert missing.response_at_ms is None
    assert missing.render_ended_at_ms is None
    assert missing.onload_at_ms is None
    assert missing.viewable_at_ms is None


def test_snapshot_rejects_negative_or_boolean_timestamps() -> None:
    raw = {
        "slots": [
            {
                "domElementId": "slot",
                "definedAtMs": -1,
                "requestedAtMs": True,
                "requestCount": -2,
            }
        ]
    }

    _, _, _, slots, _ = parse_gpt_snapshot(raw, ())

    assert slots[0].defined_at_ms is None
    assert slots[0].requested_at_ms is None
    assert slots[0].request_count == 0
