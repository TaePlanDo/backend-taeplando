"""Persistent asynchronous training-plan generation jobs."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utc_now
from app.models.enums import PlanGenerationJobStatus


class PlanGenerationJob(Base):
    """One accepted request whose plan is generated outside the HTTP response."""

    __tablename__ = "plan_generation_jobs"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    training_group_id: Mapped[UUID] = mapped_column(ForeignKey("training_groups.id"))
    participant_count: Mapped[int] = mapped_column(Integer)
    available_equipment_ids: Mapped[list[str]] = mapped_column(JSONB)
    training_type_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("training_types.id")
    )
    status: Mapped[PlanGenerationJobStatus] = mapped_column(
        SqlEnum(
            PlanGenerationJobStatus,
            name="plan_generation_job_status",
            native_enum=False,
            length=20,
        )
    )
    plan_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("training_plans.id"), unique=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
