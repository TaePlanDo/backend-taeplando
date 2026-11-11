"""Coverage for trainer-specific exercise suspension and reactivation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from app.db import exercises as exercises_db
from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    CatalogVisibility,
    EquipmentRequirementMode,
    TrainerExerciseStatus,
)
from app.models.exercises import TrainerExercise
from app.services import exercise_service
from constants import TRAINER_ID

GLOBAL_EXERCISE_ID = UUID("f48ce3a2-6f43-4127-a420-9e2cb3e7f1ca")


def test_exclude_exercise_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Suspend an exercise only for the trainer authenticated on the request."""
    with patch(
        "app.api.exercises.exercise_service.exclude_exercise", new=AsyncMock()
    ) as exclude_exercise:
        response = client.put(f"/exercises/{GLOBAL_EXERCISE_ID}/exclusion")

    assert response.status_code == 204
    exclude_exercise.assert_awaited_once_with(ANY, TRAINER_ID, GLOBAL_EXERCISE_ID)


def test_reactivate_exercise_hides_missing_or_foreign_exercises(
    client, authenticated_trainer
) -> None:
    """Avoid disclosing an exercise when it cannot be reactivated."""
    with patch(
        "app.api.exercises.exercise_service.reactivate_exercise",
        new=AsyncMock(side_effect=exercise_service.ExerciseNotFoundError),
    ):
        response = client.delete(f"/exercises/{GLOBAL_EXERCISE_ID}/exclusion")

    assert response.status_code == 404
    assert response.json() == {"detail": "Exercise not found"}


def test_exclude_exercise_suspends_the_trainer_configuration() -> None:
    """Keep temporary exclusion in the trainer-local configuration status."""
    session = MagicMock()
    session.commit = AsyncMock()
    trainer_exercise = TrainerExercise(status=TrainerExerciseStatus.ACTIVE)
    with patch(
        "app.db.exercises.get_configuration_for_trainer",
        new=AsyncMock(return_value=trainer_exercise),
    ) as get_configuration_for_trainer:
        asyncio.run(
            exercise_service.exclude_exercise(session, TRAINER_ID, GLOBAL_EXERCISE_ID)
        )

    get_configuration_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, GLOBAL_EXERCISE_ID
    )
    assert trainer_exercise.status == TrainerExerciseStatus.SUSPENDED
    session.commit.assert_awaited_once()


def test_exclude_global_exercise_creates_a_trainer_configuration() -> None:
    """A listed global exercise can be excluded before it has local settings."""
    session = MagicMock()
    session.commit = AsyncMock()
    trainer_exercise = TrainerExercise(status=TrainerExerciseStatus.ACTIVE)
    with (
        patch(
            "app.db.exercises.get_configuration_for_trainer",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.db.exercises.create_configuration_for_global_exercise",
            new=AsyncMock(return_value=trainer_exercise),
        ) as create_configuration,
    ):
        asyncio.run(
            exercise_service.exclude_exercise(session, TRAINER_ID, GLOBAL_EXERCISE_ID)
        )

    create_configuration.assert_awaited_once_with(
        session, TRAINER_ID, GLOBAL_EXERCISE_ID
    )
    assert trainer_exercise.status == TrainerExerciseStatus.SUSPENDED
    session.commit.assert_awaited_once()


def test_global_configuration_copies_the_current_approved_version() -> None:
    """The local row preserves every generation-relevant version property."""
    session = MagicMock()
    equipment = Equipment(
        id=UUID("b48ce3a2-6f43-4127-a420-9e2cb3e7f1ca"),
        name="Tarcza",
        visibility=CatalogVisibility.GLOBAL,
    )
    training_type = TrainingType(
        id=UUID("c48ce3a2-6f43-4127-a420-9e2cb3e7f1ca"),
        name="Technika",
        visibility=CatalogVisibility.GLOBAL,
    )
    segment = TrainingSegment(id=1, code="WARMUP", name="Rozgrzewka")
    session.scalar = AsyncMock(
        return_value=SimpleNamespace(
            id=UUID("a48ce3a2-6f43-4127-a420-9e2cb3e7f1ca"),
            exercise_id=GLOBAL_EXERCISE_ID,
            min_age=7,
            max_age=14,
            min_participants=2,
            max_participants=20,
            duration_minutes=10,
            equipment_requirement_mode=EquipmentRequirementMode.ALL,
            physical_difficulty=2,
            technical_difficulty=3,
            upper_body_load=4,
            lower_body_load=5,
            core_load=1,
            equipment=[equipment],
            training_types=[training_type],
            segments=[segment],
        )
    )

    trainer_exercise = asyncio.run(
        exercises_db.create_configuration_for_global_exercise(
            session, TRAINER_ID, GLOBAL_EXERCISE_ID
        )
    )

    assert trainer_exercise is not None
    assert trainer_exercise.trainer_id == TRAINER_ID
    assert trainer_exercise.exercise_id == GLOBAL_EXERCISE_ID
    assert trainer_exercise.source_version_id == UUID(
        "a48ce3a2-6f43-4127-a420-9e2cb3e7f1ca"
    )
    assert trainer_exercise.status == TrainerExerciseStatus.ACTIVE
    assert (
        trainer_exercise.min_age,
        trainer_exercise.max_age,
        trainer_exercise.min_participants,
        trainer_exercise.max_participants,
        trainer_exercise.duration_minutes,
    ) == (7, 14, 2, 20, 10)
    assert (
        trainer_exercise.physical_difficulty,
        trainer_exercise.technical_difficulty,
        trainer_exercise.upper_body_load,
        trainer_exercise.lower_body_load,
        trainer_exercise.core_load,
    ) == (2, 3, 4, 5, 1)
    assert trainer_exercise.equipment == [equipment]
    assert trainer_exercise.training_types == [training_type]
    assert trainer_exercise.segments == [segment]
    session.add.assert_called_once_with(trainer_exercise)


def test_reactivate_exercise_rejects_an_inactive_configuration() -> None:
    """Do not restore a logically deleted private exercise."""
    session = AsyncMock()
    trainer_exercise = TrainerExercise(status=TrainerExerciseStatus.INACTIVE)
    with patch(
        "app.db.exercises.get_configuration_for_trainer",
        new=AsyncMock(return_value=trainer_exercise),
    ):
        try:
            asyncio.run(
                exercise_service.reactivate_exercise(
                    session, TRAINER_ID, GLOBAL_EXERCISE_ID
                )
            )
        except exercise_service.ExerciseNotFoundError:
            pass
        else:
            raise AssertionError("Expected ExerciseNotFoundError")

    session.commit.assert_not_awaited()


def test_reactivate_exercise_restores_a_suspended_configuration() -> None:
    """Make a suspended exercise available to this trainer again."""
    session = MagicMock()
    session.commit = AsyncMock()
    trainer_exercise = TrainerExercise(status=TrainerExerciseStatus.SUSPENDED)
    with patch(
        "app.db.exercises.get_configuration_for_trainer",
        new=AsyncMock(return_value=trainer_exercise),
    ):
        asyncio.run(
            exercise_service.reactivate_exercise(
                session, TRAINER_ID, GLOBAL_EXERCISE_ID
            )
        )

    assert trainer_exercise.status == TrainerExerciseStatus.ACTIVE
    session.commit.assert_awaited_once()
