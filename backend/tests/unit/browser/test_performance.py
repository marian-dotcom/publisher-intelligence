import math

from app.browser.performance import calculate_cls, parse_performance_snapshot


def _snapshot() -> dict[str, object]:
    return {
        "schema": "pi-performance-b8/v1",
        "supported_entry_types": [
            "navigation",
            "resource",
            "largest-contentful-paint",
            "layout-shift",
            "longtask",
            "event",
            "hostile-type",
        ],
        "was_hidden": False,
        "measurement_end_ms": 2_500,
        "lcp_candidates": [120, 640],
        "layout_shifts": [[100, 0.1], [900, 0.2], [2_000, 0.4], [2_500, 0.1]],
        "interactions": [[10, 40], [10, 80], [11, 35]],
        "long_task_count": 2,
        "long_task_total_ms": 140,
        "navigation": {
            "response_start": 75,
            "dom_content_loaded_end": 350,
            "load_event_end": 500,
        },
        "resources": {
            "entry_count": 3,
            "sampled_entry_count": 3,
            "truncated": False,
            "duration_total_ms": 210,
            "transfer_size_total_bytes": 4_096,
            "initiator_counts": {"script": 2, "img": 1, "secret-url": 99},
        },
        "dom_node_count": 25,
        "errors": [],
        "samples_truncated": {},
    }


def test_cls_uses_largest_bounded_session_window() -> None:
    assert calculate_cls([(100, 0.1), (900, 0.2), (2_000, 0.4), (2_500, 0.1), (8_000, 0.3)]) == 0.5


def test_parser_preserves_synthetic_metrics_and_aggregate_resource_context() -> None:
    observation = parse_performance_snapshot(_snapshot())

    assert observation is not None
    assert observation.lcp_ms == 640
    assert observation.cls == 0.5
    assert observation.inp_ms == 80
    assert observation.inp_method == "event_timing_worst_observed_interaction_proxy"
    assert observation.ttfb_ms == 75
    assert observation.dom_content_loaded_ms == 350
    assert observation.load_event_ms == 500
    assert observation.long_task_count == 2
    assert observation.long_task_total_ms == 140
    assert observation.metadata["source"] == "synthetic_browser"
    assert observation.metadata["supported_entry_types"] == [
        "event",
        "largest-contentful-paint",
        "layout-shift",
        "longtask",
        "navigation",
        "resource",
    ]
    assert observation.metadata["resource_timing"] == {
        "entry_count": 3,
        "sampled_entry_count": 3,
        "truncated": False,
        "duration_total_ms": 210.0,
        "transfer_size_total_bytes": 4_096,
        "initiator_counts": {"img": 1, "script": 2},
    }
    assert "secret-url" not in str(observation.metadata)


def test_missing_interaction_and_unsupported_apis_stay_null_with_limitations() -> None:
    payload = _snapshot()
    payload["supported_entry_types"] = ["navigation", "resource", "layout-shift"]
    payload["interactions"] = []
    payload["layout_shifts"] = []
    observation = parse_performance_snapshot(payload)

    assert observation is not None
    assert observation.lcp_ms is None
    assert observation.cls == 0
    assert observation.inp_ms is None
    assert observation.inp_method is None
    assert observation.long_task_count is None
    assert observation.long_task_total_ms is None
    assert observation.metadata["limitations"] == [
        "lcp_api_unsupported",
        "inp_proxy_event_timing_unsupported",
        "long_task_api_unsupported",
    ]


def test_background_and_hostile_values_cannot_become_metrics() -> None:
    payload = _snapshot()
    payload["was_hidden"] = True
    payload["lcp_candidates"] = [-1, math.inf, math.nan]
    payload["layout_shifts"] = [[-1, 5], [1, -2], [2, math.inf]]
    payload["long_task_count"] = -1
    payload["long_task_total_ms"] = math.inf
    payload["dom_node_count"] = 100_000_000
    payload["navigation"] = {
        "response_start": -10,
        "dom_content_loaded_end": math.nan,
        "load_event_end": 0,
    }
    observation = parse_performance_snapshot(payload)

    assert observation is not None
    assert observation.lcp_ms is None
    assert observation.cls is None
    assert observation.ttfb_ms is None
    assert observation.dom_content_loaded_ms is None
    assert observation.load_event_ms is None
    assert observation.long_task_count is None
    assert observation.long_task_total_ms is None
    assert observation.metadata["dom_node_count"] is None
    limitations = observation.metadata["limitations"]
    assert isinstance(limitations, list)
    assert "performance_observation_backgrounded" in limitations
    assert "load_event_not_observed" in limitations
    assert parse_performance_snapshot({"schema": "hostile"}) is None
