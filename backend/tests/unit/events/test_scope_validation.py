"""EP-026 M2b-1a-2b-i — scope-validation contracts.

Proves the strict SCHEDULED validator is unchanged (missing template/scenario
keys fail exactly as before) and that DIAGNOSTIC persistence uses a dedicated
SOURCE_LEVEL validator that accepts site-level scopes without weakening
ownership or the scheduled contract.
"""

import uuid
from types import SimpleNamespace
from typing import cast

import pytest

from app.browser.models import CheckpointRun
from app.events.persistence import (
    EventStateError,
    _validate_diagnostic_scope_against_run,
    _validate_scope_against_run,
)


def _run() -> CheckpointRun:
    return cast(
        CheckpointRun,
        SimpleNamespace(
            tenant_id=uuid.uuid4(),
            site_id=uuid.uuid4(),
            template_id=uuid.uuid4(),
            scenario_id=uuid.uuid4(),
            monitored_url_id=uuid.uuid4(),
        ),
    )


def test_scheduled_validator_still_requires_template_and_scenario() -> None:
    run = _run()
    with pytest.raises(EventStateError, match="invalid event scope template_id"):
        _validate_scope_against_run(candidate_scope={"site_id": str(run.site_id)}, run=run)
    with pytest.raises(EventStateError, match="invalid event scope scenario_id"):
        _validate_scope_against_run(candidate_scope={"template_id": str(run.template_id)}, run=run)


def test_scheduled_validator_rejects_mismatched_identity() -> None:
    run = _run()
    with pytest.raises(EventStateError, match="template mismatch"):
        _validate_scope_against_run(
            candidate_scope={
                "template_id": str(uuid.uuid4()),
                "scenario_id": str(run.scenario_id),
            },
            run=run,
        )
    with pytest.raises(EventStateError, match="scenario mismatch"):
        _validate_scope_against_run(
            candidate_scope={
                "template_id": str(run.template_id),
                "scenario_id": str(uuid.uuid4()),
            },
            run=run,
        )
    with pytest.raises(EventStateError, match="monitored URL mismatch"):
        _validate_scope_against_run(
            candidate_scope={
                "template_id": str(run.template_id),
                "scenario_id": str(run.scenario_id),
                "monitored_url_id": str(uuid.uuid4()),
            },
            run=run,
        )


def test_scheduled_validator_accepts_full_matching_scope() -> None:
    run = _run()
    _validate_scope_against_run(
        candidate_scope={
            "template_id": str(run.template_id),
            "scenario_id": str(run.scenario_id),
            "monitored_url_id": str(run.monitored_url_id),
        },
        run=run,
    )


def test_diagnostic_validator_accepts_site_level_scope() -> None:
    run = _run()
    _validate_diagnostic_scope_against_run(candidate_scope={"site_id": str(run.site_id)}, run=run)


def test_diagnostic_validator_enforces_site_ownership_in_scope() -> None:
    run = _run()
    with pytest.raises(EventStateError, match="site mismatch"):
        _validate_diagnostic_scope_against_run(
            candidate_scope={"site_id": str(uuid.uuid4())}, run=run
        )


def test_diagnostic_validator_rejects_unsupported_keys() -> None:
    run = _run()
    with pytest.raises(EventStateError, match="unsupported diagnostic event scope keys"):
        _validate_diagnostic_scope_against_run(
            candidate_scope={"site_id": str(run.site_id), "subject_hash": "x"}, run=run
        )


def test_diagnostic_validator_checks_present_narrow_ids() -> None:
    run = _run()
    with pytest.raises(EventStateError, match="template mismatch"):
        _validate_diagnostic_scope_against_run(
            candidate_scope={
                "site_id": str(run.site_id),
                "template_id": str(uuid.uuid4()),
            },
            run=run,
        )
    with pytest.raises(EventStateError, match="monitored URL mismatch"):
        _validate_diagnostic_scope_against_run(
            candidate_scope={
                "site_id": str(run.site_id),
                "monitored_url_id": str(uuid.uuid4()),
            },
            run=run,
        )
    _validate_diagnostic_scope_against_run(
        candidate_scope={
            "site_id": str(run.site_id),
            "template_id": str(run.template_id),
            "scenario_id": str(run.scenario_id),
            "monitored_url_id": str(run.monitored_url_id),
        },
        run=run,
    )
