"""EP-026 M3a-1: retention execution records (append-only audit)."""

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, Integer, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Missed-execution window: twice the daily enforcement cadence.
EXPECTED_WINDOW = timedelta(days=2)


class RetentionRun(Base):
    """Append-only proof that retention actually executed.

    finished_at IS NULL truthfully represents an incomplete/failed execution;
    the error detail lives in the ENFORCE_RETENTION job lifecycle. Rows are
    never mutated after completion and are never deleted.
    """

    __tablename__ = "retention_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_deleted_per_table: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    hold_conflicts_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
