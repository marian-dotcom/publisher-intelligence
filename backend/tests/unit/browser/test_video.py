from app.browser.contracts import NetworkObservation
from app.browser.video import (
    parse_video_snapshot,
    summarize_video_network,
    video_player_stable_key,
)


def test_snapshot_keeps_player_state_and_sanitized_network_stages_separate() -> None:
    structural_path = (
        "html:nth-of-type(1)>body:nth-of-type(1)>main:nth-of-type(1)>video:nth-of-type(1)"
    )
    raw = {
        "players": [
            {
                "structural_path": structural_path,
                "present": True,
                "visible": True,
                "sticky": True,
                "fixed": True,
                "autoplay": True,
                "muted": True,
                "controls_present": True,
                "dismiss_control_present": True,
                "width_px": 360.5,
                "height_px": 202.75,
                "playback_started": True,
                "src": "https://media.example/private-user-id/video.mp4",
            }
        ],
        "errors": [],
    }
    network = [
        NetworkObservation(
            url="https://ads.example/vast/adtag",
            method="GET",
            resource_type="fetch",
            status=200,
        ),
        NetworkObservation(
            url="https://ads.example/vast/wrapper",
            method="GET",
            resource_type="fetch",
            status=502,
        ),
        NetworkObservation(
            url="https://cdn.example/media/video.mp4",
            method="GET",
            resource_type="media",
            status=206,
        ),
    ]

    players, summary, limitations, errors = parse_video_snapshot(raw, network)

    assert errors == 0
    assert summary.vast_request_count == 2
    assert summary.vast_error_count == 1
    assert summary.media_request_count == 1
    assert limitations == ["vast_payload_not_inspected"]
    assert len(players) == 1
    player = players[0]
    assert player.stable_key == video_player_stable_key(structural_path)
    assert structural_path not in player.stable_key
    assert player.present and player.visible and player.sticky and player.fixed
    assert player.autoplay and player.muted and player.controls_present
    assert player.dismiss_control_present and player.playback_started
    assert player.width_px == 360.5
    assert player.height_px == 202.75
    assert player.vast_request_count == 2
    assert player.vast_error_count == 1
    assert player.media_request_count == 1
    assert "private-user-id" not in str(players)


def test_multiple_or_opaque_players_do_not_receive_invented_network_attribution() -> None:
    network = [
        NetworkObservation(
            url="https://ads.example/vmap/ad-tag",
            method="GET",
            resource_type="fetch",
            error_text="net::ERR_FAILED",
        ),
        NetworkObservation(
            url="https://cdn.example/chunk.m4s",
            method="GET",
            resource_type="fetch",
            status=200,
        ),
    ]
    raw = {
        "players": [
            {
                "structural_path": ("html:nth-of-type(1)>body:nth-of-type(1)>video:nth-of-type(1)"),
                "present": True,
            },
            {
                "structural_path": ("html:nth-of-type(1)>body:nth-of-type(1)>video:nth-of-type(2)"),
                "present": True,
            },
            {
                "structural_path": "#user-specific-player-id",
                "present": True,
            },
        ]
    }

    players, summary, limitations, _ = parse_video_snapshot(raw, network)

    assert len(players) == 2
    assert summary.vast_request_count == 1
    assert summary.vast_error_count == 1
    assert summary.media_request_count == 1
    assert all(item.vast_request_count == 0 for item in players)
    assert all(item.media_request_count == 0 for item in players)
    assert limitations == [
        "vast_payload_not_inspected",
        "video_network_player_attribution_ambiguous",
    ]

    opaque_players, opaque_summary, opaque_limitations, _ = parse_video_snapshot({}, network)
    assert opaque_players == []
    assert opaque_summary.observed
    assert opaque_limitations == [
        "vast_payload_not_inspected",
        "video_network_player_not_observable",
    ]


def test_network_classifier_uses_only_sanitized_path_and_resource_metadata() -> None:
    observations = [
        NetworkObservation(
            url="https://example.com/content/article",
            method="GET",
            resource_type="document",
            status=200,
        ),
        NetworkObservation(
            url="https://example.com/assets/movie.webm",
            method="GET",
            resource_type="other",
            status=200,
        ),
    ]

    summary = summarize_video_network(observations)

    assert summary.vast_request_count == 0
    assert summary.vast_error_count == 0
    assert summary.media_request_count == 1
