import uuid

from app.events.evaluator import evaluate, evaluate_window
from app.events.persistence import EventRepository, EventRunResult


class EventService:
    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    async def derive(self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID) -> EventRunResult:
        value = await self._repository.load_input(
            tenant_id=tenant_id, checkpoint_run_id=checkpoint_run_id
        )
        window_values = await self._repository.load_window_inputs(
            tenant_id=tenant_id, checkpoint_run_id=checkpoint_run_id
        )
        if value is None and not window_values:
            return EventRunResult(0, 0, 0, ("NO_PREDECESSOR",))
        local = evaluate(value) if value is not None else None
        window = evaluate_window(window_values) if window_values else None
        window_codes = (
            {candidate.code for candidate in window.candidates} if window is not None else set()
        )
        local_candidates = (
            tuple(
                candidate
                for candidate in local.candidates
                if not (candidate.action == "PENDING" and candidate.code in window_codes)
            )
            if local is not None
            else ()
        )
        candidates = local_candidates + (window.candidates if window is not None else ())
        anchor = value or window_values[0]
        persistence = await self._repository.persist(anchor, candidates)
        unsupported = sum(candidate.action == "PENDING" for candidate in candidates)
        skips = (local.skip_reasons if local is not None else ("NO_PREDECESSOR",)) + (
            window.skip_reasons if window is not None else ()
        )
        return EventRunResult(
            candidate_count=len(candidates),
            persisted_count=persistence.created_count,
            unsupported_count=unsupported,
            skip_reasons=tuple(dict.fromkeys(skips)),
            updated_count=persistence.updated_count,
            resolved_count=persistence.resolved_count,
        )
