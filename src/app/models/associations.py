"""Association tables for many-to-many exercise relationships."""

from sqlalchemy import Column, ForeignKey, SmallInteger, Table
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID

from app.models.base import Base

exercise_version_equipment = Table(
    "exercise_version_equipment",
    Base.metadata,
    Column(
        "exercise_version_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("exercise_versions.id"),
        primary_key=True,
    ),
    Column(
        "equipment_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("equipment.id"),
        primary_key=True,
    ),
)

exercise_version_training_types = Table(
    "exercise_version_training_types",
    Base.metadata,
    Column(
        "exercise_version_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("exercise_versions.id"),
        primary_key=True,
    ),
    Column(
        "training_type_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("training_types.id"),
        primary_key=True,
    ),
)

exercise_version_segments = Table(
    "exercise_version_segments",
    Base.metadata,
    Column(
        "exercise_version_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("exercise_versions.id"),
        primary_key=True,
    ),
    Column(
        "segment_id",
        SmallInteger,
        ForeignKey("training_segments.id"),
        primary_key=True,
    ),
)

trainer_exercise_equipment = Table(
    "trainer_exercise_equipment",
    Base.metadata,
    Column(
        "trainer_exercise_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("trainer_exercises.id"),
        primary_key=True,
    ),
    Column(
        "equipment_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("equipment.id"),
        primary_key=True,
    ),
)

trainer_exercise_training_types = Table(
    "trainer_exercise_training_types",
    Base.metadata,
    Column(
        "trainer_exercise_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("trainer_exercises.id"),
        primary_key=True,
    ),
    Column(
        "training_type_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("training_types.id"),
        primary_key=True,
    ),
)

trainer_exercise_segments = Table(
    "trainer_exercise_segments",
    Base.metadata,
    Column(
        "trainer_exercise_id",
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("trainer_exercises.id"),
        primary_key=True,
    ),
    Column(
        "segment_id",
        SmallInteger,
        ForeignKey("training_segments.id"),
        primary_key=True,
    ),
)
