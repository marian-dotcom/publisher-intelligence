import hashlib

from app.browser.cmp import parse_tcf_snapshot, summarize_consent_dependencies
from app.browser.contracts import NetworkObservation


def test_tcf_snapshot_hashes_tc_string_and_bounds_errors() -> None:
    raw_tc_string = "fixture-sensitive-tc-string"

    parsed = parse_tcf_snapshot(
        {
            "tcfApiDetected": True,
            "capturedAtMs": 20,
            "apiReadyAtMs": 12,
            "tcStateAvailableAtMs": 18,
            "latest": {
                "tcString": raw_tc_string,
                "gdprApplies": True,
                "cmpId": 42,
                "cmpVersion": 7,
                "cmpStatus": "loaded",
                "eventStatus": "useractioncomplete",
            },
            "errors": [f"error-{index}" for index in range(30)],
        }
    )

    assert parsed["tcf_api_detected"] is True
    assert parsed["captured_at_ms"] == 20
    assert parsed["tc_string_hash"] == hashlib.sha256(raw_tc_string.encode()).hexdigest()
    assert raw_tc_string not in str(parsed)
    assert parsed["gdpr_applies"] is True
    assert parsed["cmp_id"] == 42
    assert parsed["cmp_version"] == 7
    assert parsed["event_status"] == "useractioncomplete"
    assert len(parsed["errors"]) == 20


def test_consent_dependencies_split_at_action_boundary() -> None:
    observations = [
        NetworkObservation(
            url="https://cmp.example/privacy/pre.js",
            method="GET",
            resource_type="script",
            status=200,
            observed_at_ms=10,
        ),
        NetworkObservation(
            url="https://ads.example/openrtb/bid",
            method="GET",
            resource_type="fetch",
            status=200,
            observed_at_ms=40,
        ),
        NetworkObservation(
            url="https://ads.example/openrtb/bid",
            method="GET",
            resource_type="fetch",
            status=503,
            observed_at_ms=45,
        ),
    ]

    accept = summarize_consent_dependencies(
        observations,
        action_boundary_ms=30,
        consent_path="PRIMARY",
    )

    assert {item.phase for item in accept} == {"PRE_CONSENT", "POST_ACCEPT"}
    post = next(item for item in accept if item.phase == "POST_ACCEPT")
    assert post.request_count == 2
    assert post.error_count == 1
    assert post.first_request_at_ms == 40

    reject = summarize_consent_dependencies(
        observations,
        action_boundary_ms=30,
        consent_path="REJECT",
    )
    assert {item.phase for item in reject} == {"PRE_CONSENT", "POST_REJECT"}
