"""Coverage for trainer-specific exercise suspension and reactivation."""

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from app.models.enums import TrainerExerciseStatus
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
