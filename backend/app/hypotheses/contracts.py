from app.incidents.contracts import InvestigationStateError

HYPOTHESIS_STATUSES = frozenset({"LEADING", "CONTENDER", "WEAKENED", "UNRESOLVED"})
CONFIDENCES = frozenset({"LOW", "MEDIUM", "HIGH"})
EVIDENCE_RELATIONS = frozenset({"SUPPORTS", "CONTRADICTS", "CONTEXT"})
SOURCE_KINDS = frozenset({"EVENT", "MANUAL_NOTE", "OBSERVATION_GAP"})

SUPPORT_WEIGHT = 2
CONTRADICT_WEIGHT = 1


def validate_status(status: str) -> None:
    if status not in HYPOTHESIS_STATUSES:
        raise InvestigationStateError("unknown hypothesis status")


def validate_confidence(confidence: str) -> None:
    if confidence not in CONFIDENCES:
        raise InvestigationStateError("unknown hypothesis confidence")
