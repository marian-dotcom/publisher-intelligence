import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JOB_STATUSES = ("PENDING", "RUNNING", "RETRY", "COMPLETE", "FAILED")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'RETRY', 'COMPLETE', 'FAILED')",
            name="ck_jobs_status",
        ),
        CheckConstraint("attempt >= 0", name="ck_jobs_attempt_nonnegative"),
        CheckConstraint("max_attempts > 0", name="ck_jobs_max_attempts_positive"),
        Index(
            "ix_jobs_claimable",
            "status",
            "available_at",
            "scheduled_at",
            "priority",
        ),
        Index(
            "uq_jobs_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("tenant_id IS NOT NULL AND idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_jobs_global_idempotency",
            "idempotency_key",
            unique=True,
            postgresql_where=text("tenant_id IS NULL AND idempotency_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=True
    )
    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    locked_by: Mapped[str | None] = mapped_column(String(200))
    lock_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_class: Mapped[str | None] = mapped_column(String(100))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
