import uuid
from datetime import UTC, datetime, timedelta

from app.public_config.contracts import StoredPublicConfigSnapshot
from app.public_config.evaluator import PublicConfigEvaluationInput, evaluate

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SITE_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
START = datetime(2026, 8, 21, tzinfo=UTC)


def snapshot(
    *,
    config_type: str = "ROBOTS_TXT",
    status: str = "VALID",
    semantic_hash: str | None = "a" * 64,
    broad_blocked: bool = False,
    minute: int = 0,
    fetch_kind: str = "SCHEDULED",
    validation_of: uuid.UUID | None = None,
) -> StoredPublicConfigSnapshot:
    snapshot_id = uuid.uuid4()
    summary: dict[str, object] = {}
    if semantic_hash is not None:
        summary["semantic_hash"] = semantic_hash
    if config_type == "ROBOTS_TXT":
        summary.update({"broad_blocked": broad_blocked, "rule_count": 1})
        normalizer = "robots-v1"
    else:
        summary["valid_record_count"] = 1 if status in {"VALID", "VALID_WITH_WARNINGS"} else 0
        normalizer = "ads-v1"
    return StoredPublicConfigSnapshot(
        id=snapshot_id,
        tenant_id=TENANT_ID,
        site_id=SITE_ID,
        config_type=config_type,
        observed_at=START + timedelta(minutes=minute),
        http_status=200 if status != "MISSING" else 404,
        content_hash="f" * 64,
        parse_status=status,
        artifact_id=None,
        normalizer_version=normalizer,
        summary=summary,
        fetch_kind=fetch_kind,
        validation_of_snapshot_id=validation_of,
        observation_key="e" * 64,
    )


def validation(
    primary: StoredPublicConfigSnapshot, *, status: str | None = None
) -> StoredPublicConfigSnapshot:
    minute = int((primary.observed_at - START).total_seconds() // 60) + 1
    value = snapshot(
        config_type=primary.config_type,
        status=status or primary.parse_status,
        semantic_hash=primary.summary.get("semantic_hash")
        if isinstance(primary.summary.get("semantic_hash"), str)
        else None,
        broad_blocked=primary.summary.get("broad_blocked") is True,
        minute=minute,
        fetch_kind="VALIDATION",
        validation_of=primary.id,
    )
    return value


def test_first_baseline_and_formatting_only_change_emit_no_event() -> None:
    primary = snapshot(minute=1)
    first = evaluate(PublicConfigEvaluationInput(None, primary))
    unchanged = evaluate(PublicConfigEvaluationInput(snapshot(), primary))

    assert first.candidates == ()
    assert first.skip_reasons == ("FIRST_SEMANTIC_BASELINE",)
    assert unchanged.candidates == ()
    assert unchanged.skip_reasons == ("UNCHANGED_SEMANTIC_STATE",)


def test_routine_robots_change_emits_one_specific_point() -> None:
    previous = snapshot()
    primary = snapshot(semantic_hash="b" * 64, minute=1)

    result = evaluate(PublicConfigEvaluationInput(previous, primary))

    assert [candidate.code for candidate in result.candidates] == ["ROBOTS_TXT_CHANGED"]
    assert {pointer.relation for pointer in result.candidates[0].evidence} == {"BEFORE", "AFTER"}


def test_broad_block_waits_for_agreeing_validation_and_suppresses_generic_change() -> None:
    previous = snapshot()
    primary = snapshot(semantic_hash="b" * 64, broad_blocked=True, minute=1)

    pending = evaluate(PublicConfigEvaluationInput(previous, primary))
    confirmed = evaluate(PublicConfigEvaluationInput(previous, primary, validation(primary)))
    disagreement = evaluate(
        PublicConfigEvaluationInput(previous, primary, validation(primary, status="INVALID"))
    )

    assert pending.candidates == ()
    assert [candidate.code for candidate in confirmed.candidates] == ["ROBOTS_BROAD_BLOCK_ADDED"]
    assert confirmed.candidates[0].severity == "CRITICAL"
    assert {pointer.relation for pointer in confirmed.candidates[0].evidence} == {
        "BEFORE",
        "AFTER",
        "VALIDATION",
    }
    assert disagreement.candidates == ()


def test_ads_states_are_distinct_conditions_and_repeat_is_support() -> None:
    healthy = snapshot(config_type="ADS_TXT")
    expected = {
        "MISSING": "ADS_TXT_MISSING",
        "EMPTY": "ADS_TXT_EMPTY_200",
        "INVALID": "ADS_TXT_INVALID",
    }
    for status, code in expected.items():
        primary = snapshot(config_type="ADS_TXT", status=status, semantic_hash=None, minute=1)
        first = evaluate(PublicConfigEvaluationInput(healthy, primary, validation(primary)))
        repeat_primary = snapshot(
            config_type="ADS_TXT", status=status, semantic_hash=None, minute=3
        )
        repeat = evaluate(
            PublicConfigEvaluationInput(primary, repeat_primary, validation(repeat_primary))
        )

        assert [(candidate.code, candidate.action) for candidate in first.candidates] == [
            (code, "UPSERT_CONDITION")
        ]
        assert [(candidate.code, candidate.action) for candidate in repeat.candidates] == [
            (code, "SUPPORT_CONDITION")
        ]


def test_ads_recovery_requires_agreement_and_targets_all_active_identities() -> None:
    previous = snapshot(config_type="ADS_TXT", status="MISSING", semantic_hash=None)
    primary = snapshot(config_type="ADS_TXT", minute=1)

    pending = evaluate(PublicConfigEvaluationInput(previous, primary))
    confirmed = evaluate(PublicConfigEvaluationInput(previous, primary, validation(primary)))

    assert pending.candidates == ()
    assert {candidate.code for candidate in confirmed.candidates} == {
        "ADS_TXT_MISSING",
        "ADS_TXT_EMPTY_200",
        "ADS_TXT_INVALID",
    }
    assert all(candidate.action == "RESOLVE_CONDITION" for candidate in confirmed.candidates)
    assert all(
        {pointer.relation for pointer in candidate.evidence} == {"RECOVERY", "VALIDATION"}
        for candidate in confirmed.candidates
    )
