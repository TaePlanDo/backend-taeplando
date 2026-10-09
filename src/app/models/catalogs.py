"""Equipment, training-type, and fixed training-segment catalog models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy import Enum as SqlEnum
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
from app.models.enums import CatalogVisibility

if TYPE_CHECKING:
    from app.models.exercises import ExerciseVersion, TrainerExercise
    from app.models.training import TrainingGroupSchemaItem
    from app.models.users import User


class Equipment(Base):
    """A local, pending, or global equipment catalog entry."""

    __tablename__ = "equipment"
    __table_args__ = (
        Index(
            "uq_equipment_global_name_ci",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("visibility = 'GLOBAL'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[CatalogVisibility] = mapped_column(
        SqlEnum(CatalogVisibility, name="catalog_visibility")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    owner: Mapped[User | None] = relationship("User", back_populates="owned_equipment")
    exercise_versions: Mapped[list[ExerciseVersion]] = relationship(
        "ExerciseVersion",
        secondary=exercise_version_equipment,
        back_populates="equipment",
    )
    trainer_exercises: Mapped[list[TrainerExercise]] = relationship(
        "TrainerExercise",
        secondary=trainer_exercise_equipment,
        back_populates="equipment",
    )


class TrainingType(Base):
    """A local, pending, or global training-type catalog entry."""

    __tablename__ = "training_types"
    __table_args__ = (
        Index(
            "uq_training_types_global_name_ci",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("visibility = 'GLOBAL'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))
    visibility: Mapped[CatalogVisibility] = mapped_column(
        SqlEnum(CatalogVisibility, name="catalog_visibility")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    owner: Mapped[User | None] = relationship(
        "User", back_populates="owned_training_types"
    )
    exercise_versions: Mapped[list[ExerciseVersion]] = relationship(
        "ExerciseVersion",
        secondary=exercise_version_training_types,
        back_populates="training_types",
    )
    trainer_exercises: Mapped[list[TrainerExercise]] = relationship(
        "TrainerExercise",
        secondary=trainer_exercise_training_types,
        back_populates="training_types",
    )


class TrainingSegment(Base):
    """A fixed global dictionary entry used in training schemas."""

    __tablename__ = "training_segments"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    exercise_versions: Mapped[list[ExerciseVersion]] = relationship(
        "ExerciseVersion",
        secondary=exercise_version_segments,
        back_populates="segments",
    )
    trainer_exercises: Mapped[list[TrainerExercise]] = relationship(
        "TrainerExercise",
        secondary=trainer_exercise_segments,
        back_populates="segments",
    )
    schema_items: Mapped[list[TrainingGroupSchemaItem]] = relationship(
        "TrainingGroupSchemaItem", back_populates="segment"
    )
