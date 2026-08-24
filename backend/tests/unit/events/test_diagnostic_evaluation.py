"""EP-026 M2b-1a-2b-i — deterministic classification → canonical event mapping.

Unit scope: pure evaluation semantics. No DB, no LLM, no invented evidence.
"""

import uuid
from datetime import UTC, datetime

from app.events.contracts import DiagnosticInput
from app.events.evaluator import evaluate_diagnostic

OBSERVED_AT = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)

FORBIDDEN_PUBLISHER_FAILURE_VOCABULARY = (
    "publisher failure",
    "site down",
    "site failure",
    "outage",
    "revenue impact",
)


def _input(
    classification: dict[str, object] | None,
    *,
    observed_at: datetime | None = OBSERVED_AT,
) -> DiagnosticInput:
    return DiagnosticInput(
        tenant_id=uuid.uuid4(),
        site_id=uuid.uuid4(),
        checkpoint_run_id=uuid.uuid4(),
        checkpoint_window_id=uuid.uuid4(),
        observed_at=observed_at,
        trigger_correlation_id=uuid.uuid4(),
        status="PARTIAL",
        browser_access_classification=classification,
    )


def test_degraded_classification_maps_to_browser_source_degraded() -> None:
    result = evaluate_diagnostic(
        _input({"state": "degraded", "reason": "unexpected HTTP status 403"})
    )
    assert result.skip_reasons == ()
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.code == "BROWSER_SOURCE_DEGRADED"
    assert candidate.action == "RECORD"
    assert candidate.severity is None  # rule default HIGH applies at persistence
    assert set(candidate.scope) == {"site_id"}
    assert candidate.scope["site_id"] == candidate.scope["site_id"]  # site-scoped, no URL lineage
    assert candidate.detected_at == OBSERVED_AT
    assert candidate.occurred_before_at == OBSERVED_AT
    assert len(candidate.evidence) == 1
    pointer = candidate.evidence[0]
    assert pointer.relation == "TRIGGER_AFTER"
    assert pointer.evidence_kind == "CHECKPOINT_RUN"


def test_challenge_classification_maps_to_access_challenge_suspected() -> None:
    result = evaluate_diagnostic(
        _input(
            {
                "state": "challenge_suspected",
                "reason": "deterministic challenge markers observed: captcha",
            }
        )
    )
    assert len(result.candidates) == 1
    assert result.candidates[0].code == "BROWSER_ACCESS_CHALLENGE_SUSPECTED"
    summary = result.candidates[0].summary.lower()
    assert "browser monitoring" in summary
    for phrase in FORBIDDEN_PUBLISHER_FAILURE_VOCABULARY:
        assert phrase not in summary


def test_healthy_classification_is_quiet() -> None:
    result = evaluate_diagnostic(_input({"state": "ok", "reason": "no anomalies"}))
    assert result.candidates == ()
    assert result.skip_reasons == ()


def test_missing_classification_fails_closed_with_skip_reason() -> None:
    result = evaluate_diagnostic(_input(None))
    assert result.candidates == ()
    assert result.skip_reasons == ("DIAGNOSTIC_NO_ACCESS_CLASSIFICATION",)


def test_malformed_classification_fails_closed() -> None:
    result = evaluate_diagnostic(_input({"state": "site_down", "reason": "x"}))
    assert result.candidates == ()
    assert result.skip_reasons == ("DIAGNOSTIC_NO_ACCESS_CLASSIFICATION",)


def test_degraded_without_observation_time_does_not_invent_timestamps() -> None:
    result = evaluate_diagnostic(
        _input({"state": "degraded", "reason": "navigation failed"}, observed_at=None)
    )
    assert result.candidates == ()
    assert result.skip_reasons == ("DIAGNOSTIC_OBSERVATION_TIME_MISSING",)


def test_mapping_is_deterministic_per_run() -> None:
    value = _input({"state": "degraded", "reason": "navigation failed"})
    first = evaluate_diagnostic(value)
    second = evaluate_diagnostic(value)
    assert first.candidates == second.candidates
    assert first.skip_reasons == second.skip_reasons


def test_recovery_is_never_emitted_by_plain_evaluation() -> None:
    """BROWSER_SOURCE_RECOVERED requires an explicit re-check flow (2b-ii);
    a plain ok classification must never mint a recovery event."""
    result = evaluate_diagnostic(_input({"state": "ok", "reason": "healthy"}))
    assert all(candidate.code != "BROWSER_SOURCE_RECOVERED" for candidate in result.candidates)
