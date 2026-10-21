import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.db import exercises as exercises_db
from app.db.exercises import ExercisePage, ListedExercise
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.enums import (
    AuthMethod,
    ExerciseScope,
    TrainerExerciseStatus,
)
from app.models.exercises import Exercise, TrainerExercise
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.exercises import ExerciseResponse, ExerciseUpdate, ExerciseWrite
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
        image_url="https://example.com/ap-chagi.png",
    )


def _private_configuration() -> TrainerExercise:
    """Build the private exercise's local trainer configuration."""
    return TrainerExercise(
        trainer_id=TRAINER_ID,
        exercise_id=PRIVATE_EXERCISE_ID,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
    )


def _private_response() -> ExerciseResponse:
    """Build the expected public representation of a private exercise."""
    return ExerciseResponse(
        id=PRIVATE_EXERCISE_ID,
        owner_user_id=TRAINER_ID,
        scope=ExerciseScope.PRIVATE,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        image_url="https://example.com/ap-chagi.png",
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
        status=TrainerExerciseStatus.ACTIVE,
    )


def _private_listed_exercise() -> ListedExercise:
    """Build one normalized private row returned by the database layer."""
    return ListedExercise(
        id=PRIVATE_EXERCISE_ID,
        owner_user_id=TRAINER_ID,
        scope=ExerciseScope.PRIVATE,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        image_url="https://example.com/ap-chagi.png",
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
        status=TrainerExerciseStatus.ACTIVE,
    )


def _global_listed_exercise() -> ListedExercise:
    """Build one normalized global-catalog row returned by the database layer."""
    return ListedExercise(
        id=GLOBAL_EXERCISE_ID,
        owner_user_id=CATALOG_OWNER_ID,
        scope=ExerciseScope.GLOBAL,
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        image_url="https://example.com/dollyo-chagi.png",
        min_age=8,
        max_age=18,
        min_participants=3,
        max_participants=24,
        duration_minutes=15,
        status=TrainerExerciseStatus.ACTIVE,
    )


def test_list_exercises_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Derive list ownership from authentication instead of client input."""
    responses = PaginatedResponse(
        items=[_private_response()], total=21, page=2, page_size=20, total_pages=2
    )
    with patch(
        "app.api.exercises.exercise_service.list_exercises",
        new=AsyncMock(return_value=responses),
    ) as list_exercises:
        response = client.get("/exercises?page=2&page_size=20")

    assert response.status_code == 200
    assert response.json() == {
        "items": [item.model_dump(mode="json") for item in responses.items],
        "total": 21,
        "page": 2,
        "page_size": 20,
        "total_pages": 2,
    }
    list_exercises.assert_awaited_once_with(ANY, TRAINER_ID, page=2, page_size=20)


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
                "min_age": 7,
                "max_age": 14,
                "min_participants": 2,
                "max_participants": 20,
                "duration_minutes": 10,
                "image_url": "https://example.com/ap-chagi.png",
            },
        )

    assert response.status_code == 201
    assert response.json() == response_item.model_dump(mode="json")
    payload = create_exercise.await_args.args[2]
    assert create_exercise.await_args.args[1] == TRAINER_ID
    assert payload.name == "Ap chagi"
    assert payload.description == "Kopnięcie frontalne."
    assert str(payload.image_url) == "https://example.com/ap-chagi.png"
    assert (payload.min_age, payload.max_age) == (7, 14)
    assert (payload.min_participants, payload.max_participants) == (2, 20)


def test_create_exercise_uses_default_trainer_configuration(
    client, authenticated_trainer
) -> None:
    """Use the agreed range defaults when a trainer leaves them out."""
    response_item = _private_response()
    with patch(
        "app.api.exercises.exercise_service.create_exercise",
        new=AsyncMock(return_value=response_item),
    ) as create_exercise:
        response = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Kopnięcie frontalne.",
                "duration_minutes": 10,
            },
        )

    assert response.status_code == 201
    payload = create_exercise.await_args.args[2]
    assert (payload.min_age, payload.max_age) == (1, 99)
    assert (payload.min_participants, payload.max_participants) == (1, 99)


def test_create_exercise_rejects_invalid_payload(client, authenticated_trainer) -> None:
    """Reject invalid text, URLs, ranges, and fields outside the contract."""
    configuration = {
        "min_age": 7,
        "max_age": 14,
        "min_participants": 2,
        "max_participants": 20,
    }
    with patch(
        "app.api.exercises.exercise_service.create_exercise", new=AsyncMock()
    ) as create_exercise:
        blank_name = client.post(
            "/exercises",
            json={
                "name": "   ",
                "description": "Opis",
                "duration_minutes": 10,
                **configuration,
            },
        )
        blank_description = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "   ",
                "duration_minutes": 10,
                **configuration,
            },
        )
        invalid_duration = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "duration_minutes": 0,
                **configuration,
            },
        )
        invalid_image_url = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "duration_minutes": 10,
                "image_url": "not-a-url",
                **configuration,
            },
        )
        invalid_age_range = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "min_age": 14,
                "max_age": 7,
                "min_participants": 2,
                "max_participants": 20,
                "duration_minutes": 10,
            },
        )
        invalid_participant_range = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "min_age": 7,
                "max_age": 14,
                "min_participants": 20,
                "max_participants": 2,
                "duration_minutes": 10,
            },
        )
        extra_field = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Opis",
                "duration_minutes": 10,
                "owner_user_id": str(TRAINER_ID),
                **configuration,
            },
        )

    assert blank_name.status_code == 422
    assert blank_description.status_code == 422
    assert invalid_duration.status_code == 422
    assert invalid_image_url.status_code == 422
    assert invalid_age_range.status_code == 422
    assert invalid_participant_range.status_code == 422
    assert extra_field.status_code == 422
    create_exercise.assert_not_awaited()


def test_update_exercise_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Update only the authenticated trainer's private exercise."""
    response_item = _private_response()
    with patch(
        "app.api.exercises.exercise_service.update_exercise",
        new=AsyncMock(return_value=response_item),
    ) as update_exercise:
        response = client.put(
            f"/exercises/{PRIVATE_EXERCISE_ID}",
            json={
                "name": "  Dollyo chagi  ",
                "description": "  Kopnięcie okrężne.  ",
                "duration_minutes": 15,
                "image_url": "https://example.com/dollyo-chagi.png",
            },
        )

    assert response.status_code == 200
    assert response.json() == response_item.model_dump(mode="json")
    payload = update_exercise.await_args.args[3]
    assert update_exercise.await_args.args[1:3] == (TRAINER_ID, PRIVATE_EXERCISE_ID)
    assert payload == ExerciseUpdate(
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        duration_minutes=15,
        image_url="https://example.com/dollyo-chagi.png",
    )


def test_update_exercise_rejects_non_editable_fields(
    client, authenticated_trainer
) -> None:
    """Reject configuration and ownership changes outside SCRUM-133's scope."""
    with patch(
        "app.api.exercises.exercise_service.update_exercise", new=AsyncMock()
    ) as update_exercise:
        response = client.put(
            f"/exercises/{PRIVATE_EXERCISE_ID}",
            json={
                "name": "Ap chagi",
                "description": "Kopnięcie frontalne.",
                "duration_minutes": 10,
                "min_age": 7,
            },
        )

    assert response.status_code == 422
    update_exercise.assert_not_awaited()


def test_update_exercise_hides_foreign_or_missing_exercises(
    client, authenticated_trainer
) -> None:
    """Return the same not-found result without exposing exercise ownership."""
    with patch(
        "app.api.exercises.exercise_service.update_exercise",
        new=AsyncMock(side_effect=exercise_service.ExerciseNotFoundError),
    ):
        response = client.put(
            f"/exercises/{PRIVATE_EXERCISE_ID}",
            json={
                "name": "Ap chagi",
                "description": "Kopnięcie frontalne.",
                "duration_minutes": 10,
            },
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Exercise not found"}


def test_delete_exercise_marks_an_owned_exercise_inactive(
    client, authenticated_trainer
) -> None:
    """Delegate a logical deletion using only the trainer identity from auth."""
    with patch(
        "app.api.exercises.exercise_service.delete_exercise", new=AsyncMock()
    ) as delete_exercise:
        response = client.delete(f"/exercises/{PRIVATE_EXERCISE_ID}")

    assert response.status_code == 204
    delete_exercise.assert_awaited_once_with(ANY, TRAINER_ID, PRIVATE_EXERCISE_ID)


def test_delete_exercise_hides_foreign_or_missing_exercises(
    client, authenticated_trainer
) -> None:
    """Use the same not-found response when deletion is not authorized."""
    with patch(
        "app.api.exercises.exercise_service.delete_exercise",
        new=AsyncMock(side_effect=exercise_service.ExerciseNotFoundError),
    ):
        response = client.delete(f"/exercises/{PRIVATE_EXERCISE_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Exercise not found"}


def test_list_exercises_maps_a_database_page() -> None:
    """Map a page containing private and global catalog entries."""
    session = AsyncMock()
    db_page = ExercisePage(
        items=[
            _private_listed_exercise(),
            _global_listed_exercise(),
        ],
        total=21,
    )
    with patch(
        "app.db.exercises.list_available_to_trainer",
        new=AsyncMock(return_value=db_page),
    ) as list_available:
        result = asyncio.run(
            exercise_service.list_exercises(session, TRAINER_ID, page=2, page_size=20)
        )

    assert result == PaginatedResponse(
        items=[
            _private_response(),
            ExerciseResponse(
                id=GLOBAL_EXERCISE_ID,
                owner_user_id=CATALOG_OWNER_ID,
                scope=ExerciseScope.GLOBAL,
                name="Dollyo chagi",
                description="Kopnięcie okrężne.",
                image_url="https://example.com/dollyo-chagi.png",
                min_age=8,
                max_age=18,
                min_participants=3,
                max_participants=24,
                duration_minutes=15,
                status=TrainerExerciseStatus.ACTIVE,
            ),
        ],
        total=21,
        page=2,
        page_size=20,
        total_pages=2,
    )
    list_available.assert_awaited_once_with(session, TRAINER_ID, offset=20, limit=20)


def test_list_available_to_trainer_returns_page_and_total_in_one_query() -> None:
    """Return the normalized page and its windowed total from one statement."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = [(*_private_listed_exercise(), 7)]
    session.execute = AsyncMock(return_value=result)

    page = asyncio.run(
        exercises_db.list_available_to_trainer(session, TRAINER_ID, offset=0, limit=20)
    )

    assert page.items == [_private_listed_exercise()]
    assert page.total == 7
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert "union all" in str(statement).lower()
    assert "over ()" in str(statement).lower()


def test_list_available_to_trainer_empty_first_page_skips_recount() -> None:
    """Avoid a second count query when the first page has no visible exercises."""
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = []
    session.execute = AsyncMock(return_value=result)

    page = asyncio.run(
        exercises_db.list_available_to_trainer(session, TRAINER_ID, offset=0, limit=20)
    )

    assert page == ExercisePage(items=[], total=0)
    session.execute.assert_awaited_once()


def test_list_available_to_trainer_out_of_range_page_recounts_total() -> None:
    """Keep the real total when a requested page has no rows to carry it."""
    session = AsyncMock()
    empty_page = MagicMock()
    empty_page.all.return_value = []
    count = MagicMock()
    count.scalar_one.return_value = 5
    session.execute = AsyncMock(side_effect=[empty_page, count])

    page = asyncio.run(
        exercises_db.list_available_to_trainer(session, TRAINER_ID, offset=16, limit=2)
    )

    assert page == ExercisePage(items=[], total=5)
    assert session.execute.await_count == 2
    count_statement = str(session.execute.await_args_list[1].args[0]).lower()
    assert "count(*)" in count_statement
    assert "over" not in count_statement


def test_create_exercise_builds_an_active_private_exercise() -> None:
    """Build both rows needed for a trainer-owned exercise."""
    exercise, trainer_exercise = exercises_db.create_for_trainer(
        TRAINER_ID,
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        image_url="https://example.com/ap-chagi.png",
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
    )

    assert exercise.owner_user_id == TRAINER_ID
    assert exercise.scope == ExerciseScope.PRIVATE
    assert exercise.name == "Ap chagi"
    assert exercise.description == "Kopnięcie frontalne."
    assert exercise.image_url == "https://example.com/ap-chagi.png"
    assert trainer_exercise.trainer_id == TRAINER_ID
    assert trainer_exercise.exercise is exercise
    assert trainer_exercise.status == TrainerExerciseStatus.ACTIVE
    assert trainer_exercise.duration_minutes == 10
    assert (trainer_exercise.min_age, trainer_exercise.max_age) == (7, 14)
    assert (trainer_exercise.min_participants, trainer_exercise.max_participants) == (
        2,
        20,
    )


def test_create_exercise_commits_both_new_rows() -> None:
    """Persist the exercise and its local configuration atomically."""
    session = MagicMock()
    session.commit = AsyncMock()
    exercise = _private_exercise()
    trainer_exercise = _private_configuration()
    payload = ExerciseWrite(
        name="Ap chagi",
        description="Kopnięcie frontalne.",
        image_url="https://example.com/ap-chagi.png",
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
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


def test_update_exercise_updates_all_its_editable_fields() -> None:
    """Update basic exercise data without changing trainer configuration."""
    session = MagicMock()
    session.commit = AsyncMock()
    exercise = _private_exercise()
    trainer_exercise = _private_configuration()
    payload = ExerciseUpdate(
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        duration_minutes=15,
        image_url="https://example.com/dollyo-chagi.png",
    )
    with patch(
        "app.db.exercises.get_private_for_trainer",
        new=AsyncMock(return_value=(exercise, trainer_exercise)),
    ) as get_private_for_trainer:
        result = asyncio.run(
            exercise_service.update_exercise(
                session, TRAINER_ID, PRIVATE_EXERCISE_ID, payload
            )
        )

    expected_data = _private_response().model_dump()
    expected_data.update(
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        duration_minutes=15,
        image_url="https://example.com/dollyo-chagi.png",
    )
    assert result == ExerciseResponse(**expected_data)
    assert exercise.image_url == "https://example.com/dollyo-chagi.png"
    assert (trainer_exercise.min_age, trainer_exercise.max_age) == (7, 14)
    assert (trainer_exercise.min_participants, trainer_exercise.max_participants) == (
        2,
        20,
    )
    get_private_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PRIVATE_EXERCISE_ID
    )
    session.commit.assert_awaited_once()


def test_delete_exercise_marks_the_trainer_configuration_inactive() -> None:
    """Preserve the exercise row and its historical references on deletion."""
    session = MagicMock()
    session.commit = AsyncMock()
    exercise = _private_exercise()
    trainer_exercise = _private_configuration()
    with patch(
        "app.db.exercises.get_private_for_trainer",
        new=AsyncMock(return_value=(exercise, trainer_exercise)),
    ):
        asyncio.run(
            exercise_service.delete_exercise(session, TRAINER_ID, PRIVATE_EXERCISE_ID)
        )

    assert trainer_exercise.status == TrainerExerciseStatus.INACTIVE
    assert exercise.name == "Ap chagi"
    session.commit.assert_awaited_once()
