import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.events.contracts import EvaluationInput
from app.events.persistence import PersistenceResult
from app.events.service import EventService


def _window_input(monitored_url_id: uuid.UUID) -> EvaluationInput:
    now = datetime(2026, 8, 21, tzinfo=UTC)
    tenant_id, site_id, template_id, scenario_id, window_id = (uuid.uuid4() for _ in range(5))
    seo: dict[str, object] = {
        "normalizer_version": "seo-e1-v1",
        "meta_robots": None,
        "canonical_url": "https://example.com/article",
    }
    state: dict[str, object] = {
        "scripts": {"normalizer_version": "v1"},
        "network": {"normalizer_version": "v1", "dependencies": [], "truncated": False},
        "javascript_errors": {"normalizer_version": "v1", "errors": []},
        "seo": seo,
    }
    after = {**state, "seo": {**seo, "meta_robots": "noindex"}}
    return EvaluationInput(
        tenant_id=tenant_id,
        site_id=site_id,
        monitored_url_id=monitored_url_id,
        template_id=template_id,
        scenario_id=scenario_id,
        previous_checkpoint_run_id=uuid.uuid4(),
        current_checkpoint_run_id=uuid.uuid4(),
        previous_observed_at=now,
        current_observed_at=now + timedelta(hours=6),
        previous_status="COMPLETE",
        current_status="COMPLETE",
        selection_scope="EXACT_MONITORED_URL",
        previous_state=state,
        current_state=after,
        previous_gpt={"slots": []},
        current_gpt={"slots": []},
        checkpoint_window_id=window_id,
        checkpoint_window_status="COMPLETE",
    )


class Repository:
    async def load_diagnostic_input(
        self, *, tenant_id: object, checkpoint_run_id: object
    ) -> object:
        return None

    def __init__(self, values: tuple[EvaluationInput, ...]) -> None:
        self.values = values
        self.persisted: tuple[Any, ...] = ()

    async def load_input(self, **kwargs: Any) -> None:
        return None

    async def load_window_inputs(self, **kwargs: Any) -> tuple[EvaluationInput, ...]:
        return self.values

    async def persist(
        self, value: EvaluationInput, candidates: tuple[Any, ...]
    ) -> PersistenceResult:
        self.persisted = candidates
        return PersistenceResult(created_count=1)


async def test_complete_window_still_aggregates_when_trigger_run_has_no_predecessor() -> None:
    first = _window_input(uuid.uuid4())
    second = EvaluationInput(
        **{
            field: getattr(first, field)
            for field in first.__dataclass_fields__
            if field
            not in {
                "monitored_url_id",
                "previous_checkpoint_run_id",
                "current_checkpoint_run_id",
            }
        },
        monitored_url_id=uuid.uuid4(),
        previous_checkpoint_run_id=uuid.uuid4(),
        current_checkpoint_run_id=uuid.uuid4(),
    )
    repository = Repository((first, second))
    result = await EventService(repository).derive(  # type: ignore[arg-type]
        tenant_id=first.tenant_id,
        checkpoint_run_id=uuid.uuid4(),
    )
    assert result.persisted_count == 1
    assert any(candidate.code == "NOINDEX_ADDED" for candidate in repository.persisted)
