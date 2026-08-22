import hashlib
import json
from typing import Any

from app.incidents.contracts import InvestigationStateError

EVIDENCE_PACK_TOO_LARGE = "EVIDENCE_PACK_TOO_LARGE"
MAX_PACK_BYTES = 262_144  # 256 KiB bounded pack content
PACK_ENGINE_VERSION = "pack-v1"
NOTE_SOURCE_HUMAN = "human_reported"
NOTE_SOURCE_MACHINE = "machine_observed"


def validate_relation_type(relation_type: str) -> None:
    from app.evidence.models import RELATION_TYPES

    if relation_type == "CAUSES":
        raise InvestigationStateError("CAUSES is reserved and cannot be recorded")
    if relation_type not in RELATION_TYPES:
        raise InvestigationStateError("unknown event relation type")


def validate_confidence(confidence: str | None) -> None:
    if confidence is not None and confidence not in {"LOW", "MEDIUM", "HIGH"}:
        raise InvestigationStateError("unknown relation confidence")


def validate_note_type(note_type: str) -> None:
    from app.evidence.models import NOTE_TYPES

    if note_type not in NOTE_TYPES:
        raise InvestigationStateError("unknown manual note type")


def canonical_pack_bytes(content: dict[str, Any]) -> bytes:
    """Serialize pack content deterministically (sorted keys, fixed separators)."""
    return json.dumps(content, separators=(",", ":"), sort_keys=True, default=str).encode()


def content_hash(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_pack_bytes(content)).hexdigest()
