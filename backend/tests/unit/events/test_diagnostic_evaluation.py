"""EP-026 M2b-1a-2b-i — deterministic classification → canonical event mapping.

Unit scope: pure evaluation semantics. No DB, no LLM, no invented evidence.
"""

import uuid
from datetime import UTC, datetime, timedelta

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
    """A plain ok classification without an open episode must stay quiet."""
    result = evaluate_diagnostic(_input({"state": "ok", "reason": "healthy"}))
    assert all(candidate.code != "BROWSER_SOURCE_RECOVERED" for candidate in result.candidates)


def _recovery_input(
    *,
    event_id: uuid.UUID | None = None,
    detected_at: datetime | None = None,
    run_id: uuid.UUID | None = None,
    observed_at: datetime | None = None,
    site_id: uuid.UUID | None = None,
) -> DiagnosticInput:
    return DiagnosticInput(
        tenant_id=uuid.uuid4(),
        site_id=site_id or uuid.uuid4(),
        checkpoint_run_id=uuid.uuid4(),
        checkpoint_window_id=uuid.uuid4(),
        observed_at=observed_at or OBSERVED_AT,
        trigger_correlation_id=None,
        status="COMPLETE",
        browser_access_classification={"state": "ok", "reason": "no anomalies"},
        open_degradation_event_id=event_id or uuid.uuid4(),
        open_degradation_code="BROWSER_SOURCE_DEGRADED",
        open_degradation_detected_at=detected_at or (OBSERVED_AT - timedelta(hours=1)),
        open_degradation_checkpoint_run_id=run_id or uuid.uuid4(),
    )


def test_qualifying_recheck_emits_single_recovery_event() -> None:
    from datetime import timedelta

    prior_detected = OBSERVED_AT - timedelta(hours=1)
    result = evaluate_diagnostic(
        _recovery_input(detected_at=prior_detected, observed_at=OBSERVED_AT)
    )
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.code == "BROWSER_SOURCE_RECOVERED"
    assert candidate.action == "RECORD"
    assert "publisher" not in candidate.summary.lower()
    # Truthful temporal bounds only.
    assert candidate.occurred_after_at == prior_detected
    assert candidate.detected_at == OBSERVED_AT
    relations = {pointer.relation for pointer in candidate.evidence}
    assert relations == {"BEFORE", "TRIGGER_AFTER"}


def test_pre_degradation_healthy_recheck_cannot_recover() -> None:
    """Control F: a healthy observation BEFORE the degradation evidence cannot
    recover a future episode."""
    from datetime import timedelta

    result = evaluate_diagnostic(
        _recovery_input(detected_at=OBSERVED_AT + timedelta(hours=1), observed_at=OBSERVED_AT)
    )
    assert result.candidates == ()
    assert result.skip_reasons == ()


def test_partial_episode_context_fails_closed() -> None:
    """Missing any truthful episode linkage ⇒ no recovery is invented."""
    value = _recovery_input()
    broken = DiagnosticInput(
        tenant_id=value.tenant_id,
        site_id=value.site_id,
        checkpoint_run_id=value.checkpoint_run_id,
        checkpoint_window_id=value.checkpoint_window_id,
        observed_at=value.observed_at,
        trigger_correlation_id=None,
        status="COMPLETE",
        browser_access_classification={"state": "ok", "reason": "no anomalies"},
        open_degradation_event_id=value.open_degradation_event_id,
        open_degradation_code=value.open_degradation_code,
        open_degradation_detected_at=value.open_degradation_detected_at,
        open_degradation_checkpoint_run_id=None,  # trigger run unknown
    )
    result = evaluate_diagnostic(broken)
    assert result.candidates == ()


def test_same_run_cannot_recover_itself() -> None:
    value = _recovery_input(run_id=None)
    assert value.open_degradation_checkpoint_run_id is not None
    same_run = DiagnosticInput(
        tenant_id=value.tenant_id,
        site_id=value.site_id,
        checkpoint_run_id=value.open_degradation_checkpoint_run_id,
        checkpoint_window_id=value.checkpoint_window_id,
        observed_at=value.observed_at,
        trigger_correlation_id=None,
        status="COMPLETE",
        browser_access_classification=value.browser_access_classification,
        open_degradation_event_id=value.open_degradation_event_id,
        open_degradation_code=value.open_degradation_code,
        open_degradation_detected_at=value.open_degradation_detected_at,
        open_degradation_checkpoint_run_id=value.open_degradation_checkpoint_run_id,
    )
    result = evaluate_diagnostic(same_run)
    assert result.candidates == ()
