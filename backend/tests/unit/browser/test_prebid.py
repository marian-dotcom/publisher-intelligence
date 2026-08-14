from app.browser.contracts import NetworkObservation
from app.browser.prebid import (
    first_ad_server_request_at_ms,
    parse_prebid_snapshot,
    prebid_server_endpoint_observed,
)


def test_snapshot_aggregates_safe_auction_and_bidder_evidence() -> None:
    raw = {
        "present": True,
        "observable": True,
        "version": "11.15.0",
        "captured_at_ms": 100,
        "configured_timeout_ms": 1_000,
        "configured_ad_unit_count": 2,
        "installed_modules": ["consentManagementTcf", "floors"],
        "targeting_keys": ["hb_bidder", "hb_pb", "hb_adid"],
        "events": [
            {
                "event_type": "addAdUnits",
                "auction_key": "auction-unassigned",
                "elapsed_at_ms": 5,
            },
            {
                "event_type": "auctionInit",
                "auction_key": "auction-001",
                "elapsed_at_ms": 10,
            },
            {
                "event_type": "bidRequested",
                "auction_key": "auction-001",
                "bidder_code": "fast-bidder",
                "elapsed_at_ms": 20,
            },
            {
                "event_type": "bidResponse",
                "auction_key": "auction-001",
                "bidder_code": "fast-bidder",
                "elapsed_at_ms": 80,
                "response_time_ms": 60,
                "cpm": 99.99,
                "bid_id": "must-not-survive",
            },
            {
                "event_type": "bidRequested",
                "auction_key": "auction-001",
                "bidder_code": "slow-bidder",
                "elapsed_at_ms": 22,
            },
            {
                "event_type": "bidTimeout",
                "auction_key": "auction-001",
                "bidder_code": "slow-bidder",
                "elapsed_at_ms": 1_010,
            },
            {
                "event_type": "bidWon",
                "auction_key": "auction-001",
                "bidder_code": "fast-bidder",
                "elapsed_at_ms": 1_020,
            },
            {
                "event_type": "auctionEnd",
                "auction_key": "auction-001",
                "elapsed_at_ms": 1_015,
            },
        ],
    }
    network = [
        NetworkObservation(
            url="https://securepubads.g.doubleclick.net/gampad/ads",
            method="GET",
            resource_type="fetch",
            status=200,
            request_started_at_ms=50,
            observed_at_ms=90,
        ),
        NetworkObservation(
            url="https://securepubads.g.doubleclick.net/gampad/ads",
            method="GET",
            resource_type="fetch",
            status=200,
            request_started_at_ms=1_140,
            observed_at_ms=1_180,
        ),
    ]

    result = parse_prebid_snapshot(raw, network, network_clock_ms=200)
    present, observable, version, server_side, modules, keys, auctions, bidders = result

    assert present and observable and not server_side
    assert version == "11.15.0"
    assert modules == ["consentManagementTcf", "floors"]
    assert keys == ["hb_adid", "hb_bidder", "hb_pb"]
    assert len(auctions) == 1
    auction = auctions[0]
    assert auction.auction_key == "auction-001"
    assert auction.started_at_ms == 110
    assert auction.ended_at_ms == 1_115
    assert auction.configured_timeout_ms == 1_000
    assert auction.ad_unit_count == 2
    assert auction.bidder_request_count == 2
    assert auction.bid_response_count == 1
    assert auction.timeout_count == 1
    assert auction.first_ad_server_request_at_ms == 1_140

    by_code = {item.bidder_code: item for item in bidders}
    assert by_code["fast-bidder"].response_time_ms_avg == 60
    assert by_code["fast-bidder"].winning_bid_count == 1
    assert by_code["slow-bidder"].timeout_count == 1
    assert "must-not-survive" not in str(result)
    assert "99.99" not in str(result)


def test_network_helpers_distinguish_server_endpoint_and_gam_start() -> None:
    observations = [
        NetworkObservation(
            url="https://pbs.example.com/openrtb2/auction",
            method="POST",
            resource_type="fetch",
            status=200,
            request_started_at_ms=50,
        ),
        NetworkObservation(
            url="https://securepubads.g.doubleclick.net/gampad/ads",
            method="GET",
            resource_type="fetch",
            status=200,
            request_started_at_ms=90,
        ),
    ]

    assert prebid_server_endpoint_observed(observations)
    assert first_ad_server_request_at_ms(observations) == 90
    assert first_ad_server_request_at_ms(observations, after_ms=91) is None
