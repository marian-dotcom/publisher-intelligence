import uuid

from app.events.evaluator import evaluate
from app.events.persistence import EventRepository, EventRunResult


class EventService:
    def __init__(self, repository: EventRepository) -> None:
        self._repository = repository

    async def derive(self, *, tenant_id: uuid.UUID, checkpoint_run_id: uuid.UUID) -> EventRunResult:
        value = await self._repository.load_input(
            tenant_id=tenant_id, checkpoint_run_id=checkpoint_run_id
        )
        if value is None:
            return EventRunResult(0, 0, 0, ("NO_PREDECESSOR",))
        result = evaluate(value)
        persisted = await self._repository.persist(value, result.candidates)
        unsupported = sum(
            candidate.confirmation != "SINGLE_STRONG_OBSERVATION" for candidate in result.candidates
        )
        return EventRunResult(len(result.candidates), persisted, unsupported, result.skip_reasons)
