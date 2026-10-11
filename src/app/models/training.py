"""Training-group schemas and immutable historical training-plan models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utc_now

if TYPE_CHECKING:
    from app.models.catalogs import TrainingSegment
    from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise
    from app.models.users import User


class TrainingGroup(Base):
    """A trainer-owned group with one current ordered training schema."""

    __tablename__ = "training_groups"
    __table_args__ = (
        CheckConstraint("min_age > 0", name="ck_training_groups_min_age"),
        CheckConstraint("max_age >= min_age", name="ck_training_groups_age_range"),
        CheckConstraint(
            "duration_minutes > 0", name="ck_training_groups_duration_minutes"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    trainer: Mapped[User] = relationship("User", back_populates="training_groups")
    schema_items: Mapped[list[TrainingGroupSchemaItem]] = relationship(
        "TrainingGroupSchemaItem",
        back_populates="training_group",
        cascade="all, delete-orphan",
    )
    training_plans: Mapped[list[TrainingPlan]] = relationship(
        "TrainingPlan", back_populates="training_group", cascade="all, delete-orphan"
    )


class TrainingGroupSchemaItem(Base):
    """One ordered segment occurrence in a group's training schema."""

    __tablename__ = "training_group_schema_items"
    __table_args__ = (
        UniqueConstraint("training_group_id", "position"),
        CheckConstraint("percentage > 0", name="ck_schema_items_percentage_positive"),
        CheckConstraint("percentage <= 100", name="ck_schema_items_percentage_max"),
        CheckConstraint("position > 0", name="ck_schema_items_position"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    training_group_id: Mapped[UUID] = mapped_column(ForeignKey("training_groups.id"))
    segment_id: Mapped[int] = mapped_column(ForeignKey("training_segments.id"))
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    position: Mapped[int] = mapped_column(Integer)

    training_group: Mapped[TrainingGroup] = relationship(
        "TrainingGroup", back_populates="schema_items"
    )
    segment: Mapped[TrainingSegment] = relationship(
        "TrainingSegment", back_populates="schema_items"
    )


class TrainingPlan(Base):
    """An immutable historical training plan with input snapshots."""

    __tablename__ = "training_plans"
    __table_args__ = (
        CheckConstraint(
            "participant_count > 0", name="ck_training_plans_participant_count"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    training_group_id: Mapped[UUID] = mapped_column(ForeignKey("training_groups.id"))
    participant_count: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    group_name_snapshot: Mapped[str] = mapped_column(String(255))
    group_min_age_snapshot: Mapped[int] = mapped_column(Integer)
    group_max_age_snapshot: Mapped[int] = mapped_column(Integer)
    training_duration_snapshot: Mapped[int] = mapped_column(Integer)
    available_equipment_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    training_types_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    schema_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    trainer: Mapped[User] = relationship("User", back_populates="training_plans")
    training_group: Mapped[TrainingGroup] = relationship(
        "TrainingGroup", back_populates="training_plans"
    )
    exercises: Mapped[list[TrainingPlanExercise]] = relationship(
        "TrainingPlanExercise",
        back_populates="training_plan",
        cascade="all, delete-orphan",
    )


class TrainingPlanExercise(Base):
    """One exercise occurrence in a historical training-plan snapshot."""

    __tablename__ = "training_plan_exercises"
    __table_args__ = (
        UniqueConstraint("training_plan_id", "position"),
        CheckConstraint("position > 0", name="ck_plan_exercises_position"),
        CheckConstraint(
            "schema_position > 0", name="ck_plan_exercises_schema_position"
        ),
        CheckConstraint(
            "duration_minutes_snapshot > 0",
            name="ck_plan_exercises_duration_minutes",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    training_plan_id: Mapped[UUID] = mapped_column(ForeignKey("training_plans.id"))
    trainer_exercise_id: Mapped[UUID] = mapped_column(
        ForeignKey("trainer_exercises.id")
    )
    exercise_id: Mapped[UUID] = mapped_column(ForeignKey("exercises.id"))
    exercise_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exercise_versions.id")
    )
    position: Mapped[int] = mapped_column(Integer)
    schema_position: Mapped[int] = mapped_column(Integer)
    name_snapshot: Mapped[str] = mapped_column(String(255))
    description_snapshot: Mapped[str] = mapped_column(Text)
    min_age_snapshot: Mapped[int] = mapped_column(Integer)
    max_age_snapshot: Mapped[int] = mapped_column(Integer)
    min_participants_snapshot: Mapped[int] = mapped_column(Integer)
    max_participants_snapshot: Mapped[int] = mapped_column(Integer)
    duration_minutes_snapshot: Mapped[int] = mapped_column(Integer)
    equipment_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    training_types_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    segments_snapshot: Mapped[list[dict[str, object]]] = mapped_column(JSONB)

    training_plan: Mapped[TrainingPlan] = relationship(
        "TrainingPlan", back_populates="exercises"
    )
    trainer_exercise: Mapped[TrainerExercise] = relationship(
        "TrainerExercise", back_populates="plan_exercises"
    )
    exercise: Mapped[Exercise] = relationship("Exercise")
    exercise_version: Mapped[ExerciseVersion | None] = relationship("ExerciseVersion")
