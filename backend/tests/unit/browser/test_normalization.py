from app.browser.contracts import JavaScriptError, NetworkObservation
from app.browser.normalization import (
    dependency_identity,
    normalize_dom,
    normalize_javascript_errors,
    normalize_network,
    normalize_scripts,
)


def test_dom_normalization_ignores_copy_and_volatile_values() -> None:
    first = normalize_dom(
        """<html><head><meta name="robots" content="index,follow"></head>
        <body><main id="story-123456"><h1>First headline</h1>
        <div class="ad-slot slot-987654" style="position: sticky; color: red"></div>
        <p>Article copy at 2026-08-14 12:00</p></main></body></html>"""
    )
    second = normalize_dom(
        """<html><head><meta name="robots" content="index,follow"></head>
        <body><main id="story-777777"><h1>Different headline</h1>
        <div class="slot-555555 ad-slot" style="color: blue; position: sticky"></div>
        <p>Completely different article text</p></main></body></html>"""
    )

    assert first["sha256"] == second["sha256"]
    assert "headline" not in str(first).lower()
    assert "article copy" not in str(first).lower()


def test_meaningful_structure_changes_dom_hash() -> None:
    before = normalize_dom("<html><body><main><div class='ad-slot'></div></main></body></html>")
    after = normalize_dom("<html><body><main><aside class='ad-slot'></aside></main></body></html>")

    assert before["sha256"] != after["sha256"]


def test_dependency_identity_removes_queries_and_path_ids() -> None:
    first = dependency_identity(
        "https://bidder.example.com/openrtb2/123456?auctionId=secret-one", "xhr"
    )
    second = dependency_identity(
        "https://bidder.example.com/openrtb2/999999?auctionId=secret-two", "xhr"
    )

    assert first == second
    assert first is not None
    assert "secret" not in str(first)
    assert first["category"] == "HEADER_BIDDING_SSP"


def test_script_and_network_normalization_is_stable_and_aggregated() -> None:
    scripts = normalize_scripts(
        [
            "https://cdn.example.com/app.js?v=one",
            "https://cdn.example.com/app.js?v=two",
        ]
    )
    network = normalize_network(
        [
            NetworkObservation(
                url="https://cdn.example.com/app.js?v=secret",
                method="GET",
                resource_type="script",
                status=200,
            ),
            NetworkObservation(
                url="https://cdn.example.com/app.js?v=another",
                method="GET",
                resource_type="script",
                status=503,
            ),
        ]
    )

    assert len(scripts["identities"]) == 1
    assert len(network["dependencies"]) == 1
    dependency = network["dependencies"][0]
    assert dependency["request_count"] == 2
    assert dependency["status_5xx"] == 1
    assert "secret" not in str(network)


def test_javascript_error_fingerprint_removes_volatile_identifiers() -> None:
    first = normalize_javascript_errors(
        [
            JavaScriptError(
                message="Auction 123456 failed token abcdef1234567890",
                source="https://cdn.example.com/app/123456/main.js?token=secret",
            )
        ]
    )
    second = normalize_javascript_errors(
        [
            JavaScriptError(
                message="Auction 999999 failed token fedcba0987654321",
                source="https://cdn.example.com/app/999999/main.js?token=other",
            )
        ]
    )

    assert first["errors"][0]["fingerprint"] == second["errors"][0]["fingerprint"]
    assert "secret" not in str(first)
