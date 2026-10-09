"""Exercise, versioning, and trainer-specific exercise configuration models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.associations import (
    exercise_version_equipment,
    exercise_version_segments,
    exercise_version_training_types,
    trainer_exercise_equipment,
    trainer_exercise_segments,
    trainer_exercise_training_types,
)
from app.models.base import Base, utc_now
from app.models.enums import (
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
)

if TYPE_CHECKING:
    from app.models.catalogs import Equipment, TrainingSegment, TrainingType
    from app.models.training import TrainingPlanExercise
    from app.models.users import User


class Exercise(Base):
    """The logical exercise, private or published globally."""

    __tablename__ = "exercises"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    owner_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    scope: Mapped[ExerciseScope] = mapped_column(
        SqlEnum(ExerciseScope, name="exercise_scope")
    )
    image_url: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    latest_approved_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "exercise_versions.id",
            name="fk_exercises_latest_approved_version",
            use_alter=True,
        )
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    owner: Mapped[User] = relationship("User", back_populates="owned_exercises")
    versions: Mapped[list[ExerciseVersion]] = relationship(
        "ExerciseVersion",
        back_populates="exercise",
        foreign_keys="ExerciseVersion.exercise_id",
        cascade="all, delete-orphan",
    )
    latest_approved_version: Mapped[ExerciseVersion | None] = relationship(
        "ExerciseVersion",
        foreign_keys=[latest_approved_version_id],
        post_update=True,
    )
    trainer_exercises: Mapped[list[TrainerExercise]] = relationship(
        "TrainerExercise", back_populates="exercise"
    )


class ExerciseVersion(Base):
    """An immutable moderation version of a global exercise."""

    __tablename__ = "exercise_versions"
    __table_args__ = (
        UniqueConstraint("exercise_id", "version_number"),
        CheckConstraint(
            "version_number > 0", name="ck_exercise_versions_version_number"
        ),
        CheckConstraint("min_age > 0", name="ck_exercise_versions_min_age"),
        CheckConstraint("max_age >= min_age", name="ck_exercise_versions_age_range"),
        CheckConstraint(
            "min_participants > 0", name="ck_exercise_versions_min_participants"
        ),
        CheckConstraint(
            "max_participants >= min_participants",
            name="ck_exercise_versions_participant_range",
        ),
        CheckConstraint(
            "duration_minutes > 0", name="ck_exercise_versions_duration_minutes"
        ),
        Index(
            "uq_exercise_versions_pending",
            "exercise_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    exercise_id: Mapped[UUID] = mapped_column(ForeignKey("exercises.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[ExerciseVersionStatus] = mapped_column(
        SqlEnum(ExerciseVersionStatus, name="exercise_version_status")
    )
    image_url: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    min_participants: Mapped[int] = mapped_column(Integer)
    max_participants: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    exercise: Mapped[Exercise] = relationship(
        "Exercise", back_populates="versions", foreign_keys=[exercise_id]
    )
    equipment: Mapped[list[Equipment]] = relationship(
        "Equipment",
        secondary=exercise_version_equipment,
        back_populates="exercise_versions",
    )
    training_types: Mapped[list[TrainingType]] = relationship(
        "TrainingType",
        secondary=exercise_version_training_types,
        back_populates="exercise_versions",
    )
    segments: Mapped[list[TrainingSegment]] = relationship(
        "TrainingSegment",
        secondary=exercise_version_segments,
        back_populates="exercise_versions",
    )


class TrainerExercise(Base):
    """A trainer's local configuration of a source exercise."""

    __tablename__ = "trainer_exercises"
    __table_args__ = (
        UniqueConstraint("trainer_id", "exercise_id"),
        CheckConstraint("min_age > 0", name="ck_trainer_exercises_min_age"),
        CheckConstraint("max_age >= min_age", name="ck_trainer_exercises_age_range"),
        CheckConstraint(
            "min_participants > 0", name="ck_trainer_exercises_min_participants"
        ),
        CheckConstraint(
            "max_participants >= min_participants",
            name="ck_trainer_exercises_participant_range",
        ),
        CheckConstraint(
            "duration_minutes > 0", name="ck_trainer_exercises_duration_minutes"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    exercise_id: Mapped[UUID] = mapped_column(ForeignKey("exercises.id"))
    source_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("exercise_versions.id")
    )
    status: Mapped[TrainerExerciseStatus] = mapped_column(
        SqlEnum(TrainerExerciseStatus, name="trainer_exercise_status")
    )
    min_age: Mapped[int] = mapped_column(Integer)
    max_age: Mapped[int] = mapped_column(Integer)
    min_participants: Mapped[int] = mapped_column(Integer)
    max_participants: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    trainer: Mapped[User] = relationship("User", back_populates="trainer_exercises")
    exercise: Mapped[Exercise] = relationship(
        "Exercise", back_populates="trainer_exercises"
    )
    source_version: Mapped[ExerciseVersion | None] = relationship(
        "ExerciseVersion", foreign_keys=[source_version_id]
    )
    equipment: Mapped[list[Equipment]] = relationship(
        "Equipment",
        secondary=trainer_exercise_equipment,
        back_populates="trainer_exercises",
    )
    training_types: Mapped[list[TrainingType]] = relationship(
        "TrainingType",
        secondary=trainer_exercise_training_types,
        back_populates="trainer_exercises",
    )
    segments: Mapped[list[TrainingSegment]] = relationship(
        "TrainingSegment",
        secondary=trainer_exercise_segments,
        back_populates="trainer_exercises",
    )
    plan_exercises: Mapped[list[TrainingPlanExercise]] = relationship(
        "TrainingPlanExercise", back_populates="trainer_exercise"
    )
