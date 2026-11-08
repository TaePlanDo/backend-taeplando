"""Coverage for planning attributes exposed by the exercise API."""

from uuid import UUID

from app.db import exercises as exercises_db
from app.models.enums import EquipmentRequirementMode
from app.schemas.exercises import ExerciseWrite
from constants import TRAINER_ID
from exercise_planning_fixtures import private_planning_attributes


def test_create_for_trainer_preserves_planning_attributes() -> None:
    """Keep all planning metadata on the trainer-local exercise configuration."""
    _, trainer_exercise = exercises_db.create_for_trainer(
        TRAINER_ID,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        image_url=None,
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
        **private_planning_attributes(),
    )

    assert trainer_exercise.equipment_requirement_mode == EquipmentRequirementMode.ANY
    assert (
        trainer_exercise.physical_difficulty,
        trainer_exercise.technical_difficulty,
        trainer_exercise.upper_body_load,
        trainer_exercise.lower_body_load,
        trainer_exercise.core_load,
    ) == (2, 4, 3, 5, 1)


def test_exercise_write_defaults_planning_attributes() -> None:
    """Keep the create API backwards compatible with neutral planning defaults."""
    payload = ExerciseWrite(
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        duration_minutes=10,
        equipment_ids=[],
        training_type_ids=[UUID("2894e3b8-d31a-42a3-89df-fbff1dfb1fb2")],
        segment_ids=[3],
    )

    assert payload.equipment_requirement_mode == EquipmentRequirementMode.ALL
    assert (
        payload.physical_difficulty,
        payload.technical_difficulty,
        payload.upper_body_load,
        payload.lower_body_load,
        payload.core_load,
    ) == (3, 3, 3, 3, 3)
