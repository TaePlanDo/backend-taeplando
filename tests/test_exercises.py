import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.db import exercises as exercises_db
from app.db.exercises import ListedExercise
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.enums import (
    AuthMethod,
    ExerciseScope,
    ExerciseVersionStatus,
    TrainerExerciseStatus,
)
from app.models.exercises import Exercise, ExerciseVersion, TrainerExercise
from app.models.users import User
from app.schemas.exercises import ExerciseResponse, ExerciseWrite
from app.services import exercise_service

TRAINER_ID = UUID("d9aa16f7-b30a-4887-890b-247f86a2eef5")
CATALOG_OWNER_ID = UUID("3cae14d4-cf8b-4f55-a34d-b169404d2f49")
PRIVATE_EXERCISE_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
GLOBAL_EXERCISE_ID = UUID("f48ce3a2-6f43-4127-a420-9e2cb3e7f1ca")


@pytest.fixture
def authenticated_trainer() -> None:
    """Authenticate exercise route tests without JWT parsing."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id=TRAINER_ID,
        email="trainer@example.com",
        full_name="Trainer",
        auth_method=AuthMethod.LOCAL,
        password_hash="hash",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _private_exercise() -> Exercise:
    """Build a private exercise owned by the authenticated trainer."""
    return Exercise(
        id=PRIVATE_EXERCISE_ID,
        owner_user_id=TRAINER_ID,
        scope=ExerciseScope.PRIVATE,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
    )


def _private_configuration() -> TrainerExercise:
    """Build the private exercise's local trainer configuration."""
    return TrainerExercise(
        trainer_id=TRAINER_ID,
        exercise_id=PRIVATE_EXERCISE_ID,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=1,
        max_age=99,
        min_participants=1,
        max_participants=99,
        duration_minutes=10,
    )


def _global_exercise() -> Exercise:
    """Build a globally shared logical exercise."""
    return Exercise(
        id=GLOBAL_EXERCISE_ID,
        owner_user_id=CATALOG_OWNER_ID,
        scope=ExerciseScope.GLOBAL,
        name="Outdated name",
        description="Outdated description.",
    )


def _approved_version() -> ExerciseVersion:
    """Build the public catalog version used in a global response."""
    return ExerciseVersion(
        exercise_id=GLOBAL_EXERCISE_ID,
        version_number=1,
        status=ExerciseVersionStatus.APPROVED,
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        min_age=1,
        max_age=99,
        min_participants=1,
        max_participants=99,
        duration_minutes=15,
    )


def _private_response() -> ExerciseResponse:
    """Build the expected public representation of a private exercise."""
    return ExerciseResponse(
        id=PRIVATE_EXERCISE_ID,
        owner_user_id=TRAINER_ID,
        scope=ExerciseScope.PRIVATE,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        duration_minutes=10,
        status=TrainerExerciseStatus.ACTIVE,
    )


def test_list_exercises_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Derive list ownership from authentication instead of client input."""
    responses = [_private_response()]
    with patch(
        "app.api.exercises.exercise_service.list_exercises",
        new=AsyncMock(return_value=responses),
    ) as list_exercises:
        response = client.get("/exercises")

    assert response.status_code == 200
    assert response.json() == [item.model_dump(mode="json") for item in responses]
    list_exercises.assert_awaited_once_with(ANY, TRAINER_ID)


def test_create_exercise_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Derive the new exercise owner from authentication, never from the body."""
    response_item = _private_response()
    with patch(
        "app.api.exercises.exercise_service.create_exercise",
        new=AsyncMock(return_value=response_item),
    ) as create_exercise:
        response = client.post(
            "/exercises",
            json={
                "name": "  Ap chagi  ",
                "description": "  Kopnięcie frontalne.  ",
                "duration_minutes": 10,
            },
        )

    assert response.status_code == 201
    assert response.json() == response_item.model_dump(mode="json")
    payload = create_exercise.await_args.args[2]
    assert create_exercise.await_args.args[1] == TRAINER_ID
    assert payload.name == "Ap chagi"
    assert payload.description == "Kopnięcie frontalne."


def test_create_exercise_rejects_invalid_payload(client, authenticated_trainer) -> None:
    """Reject blank text, invalid duration, and fields outside the contract."""
    with patch(
        "app.api.exercises.exercise_service.create_exercise", new=AsyncMock()
    ) as create_exercise:
        blank_name = client.post(
            "/exercises",
            json={"name": "   ", "description": "Opis", "duration_minutes": 10},
        )
        blank_description = client.post(
            "/exercises",
            json={"name": "Ap chagi", "description": "   ", "duration_minutes": 10},
        )
        invalid_duration = client.post(
            "/exercises",
            json={"name": "Ap chagi", "description": "Opis", "duration_minutes": 0},
        )
        extra_field = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "duration_minutes": 10,
                "owner_user_id": str(TRAINER_ID),
            },
        )

    assert blank_name.status_code == 422
    assert blank_description.status_code == 422
    assert invalid_duration.status_code == 422
    assert extra_field.status_code == 422
    create_exercise.assert_not_awaited()


def test_list_exercises_maps_private_and_global_catalog_entries() -> None:
    """Return trainer data for private entries and approved data for global ones."""
    session = AsyncMock()
    private = _private_exercise()
    private_configuration = _private_configuration()
    global_exercise = _global_exercise()
    approved_version = _approved_version()
    listed_exercises = [
        ListedExercise(private, private_configuration, None),
        ListedExercise(global_exercise, None, approved_version),
    ]
    with patch(
        "app.db.exercises.list_available_to_trainer",
        new=AsyncMock(return_value=listed_exercises),
    ) as list_available:
        result = asyncio.run(exercise_service.list_exercises(session, TRAINER_ID))

    assert result == [
        _private_response(),
        ExerciseResponse(
            id=GLOBAL_EXERCISE_ID,
            owner_user_id=CATALOG_OWNER_ID,
            scope=ExerciseScope.GLOBAL,
            name="Dollyo chagi",
            description="Kopnięcie okrężne.",
            duration_minutes=15,
            status=TrainerExerciseStatus.ACTIVE,
        ),
    ]
    list_available.assert_awaited_once_with(session, TRAINER_ID)


def test_create_exercise_builds_an_active_private_exercise() -> None:
    """Build both rows needed for a trainer-owned exercise."""
    exercise, trainer_exercise = exercises_db.create_for_trainer(
        TRAINER_ID,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        duration_minutes=10,
    )

    assert exercise.owner_user_id == TRAINER_ID
    assert exercise.scope == ExerciseScope.PRIVATE
    assert exercise.name == "Ap chagi"
    assert exercise.description == "Kopnięcie frontalne."
    assert trainer_exercise.trainer_id == TRAINER_ID
    assert trainer_exercise.exercise is exercise
    assert trainer_exercise.status == TrainerExerciseStatus.ACTIVE
    assert trainer_exercise.duration_minutes == 10
    assert (trainer_exercise.min_age, trainer_exercise.max_age) == (1, 99)
    assert (trainer_exercise.min_participants, trainer_exercise.max_participants) == (
        1,
        99,
    )


def test_create_exercise_commits_both_new_rows() -> None:
    """Persist the exercise and its local configuration atomically."""
    session = MagicMock()
    session.commit = AsyncMock()
    exercise = _private_exercise()
    trainer_exercise = _private_configuration()
    payload = ExerciseWrite(
        name="Ap chagi", description="Kopnięcie frontalne.", duration_minutes=10
    )
    with patch(
        "app.db.exercises.create_for_trainer",
        return_value=(exercise, trainer_exercise),
    ):
        result = asyncio.run(
            exercise_service.create_exercise(session, TRAINER_ID, payload)
        )

    assert result == _private_response()
    session.add_all.assert_called_once_with((exercise, trainer_exercise))
    session.commit.assert_awaited_once()
