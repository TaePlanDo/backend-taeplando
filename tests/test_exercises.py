import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.db import exercises as exercises_db
from app.db.exercises import ExerciseConfiguration, ExercisePage, ListedExercise
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.catalogs import Equipment, TrainingSegment, TrainingType
from app.models.enums import (
    AuthMethod,
    CatalogVisibility,
    ExerciseScope,
    TrainerExerciseStatus,
)
from app.models.exercises import Exercise, TrainerExercise
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.exercises import (
    CatalogReference,
    ExerciseResponse,
    ExerciseUpdate,
    ExerciseWrite,
    TrainingSegmentResponse,
)
from app.services import exercise_service

TRAINER_ID = UUID("d9aa16f7-b30a-4887-890b-247f86a2eef5")
CATALOG_OWNER_ID = UUID("3cae14d4-cf8b-4f55-a34d-b169404d2f49")
PRIVATE_EXERCISE_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
GLOBAL_EXERCISE_ID = UUID("f48ce3a2-6f43-4127-a420-9e2cb3e7f1ca")
TRAINER_EXERCISE_ID = UUID("99bcecb1-5da4-48dd-9d91-df41c8e6f579")
GLOBAL_VERSION_ID = UUID("e5a3ed0d-f8e3-405e-ab66-060642a15df7")
EQUIPMENT_ID = UUID("410327de-b35a-4dcf-8b99-5249e159ce06")
TRAINING_TYPE_ID = UUID("2894e3b8-d31a-42a3-89df-fbff1dfb1fb2")
SEGMENT_ID = 3


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
        id=TRAINER_EXERCISE_ID,
        trainer_id=TRAINER_ID,
        exercise_id=PRIVATE_EXERCISE_ID,
        status=TrainerExerciseStatus.ACTIVE,
        min_age=7,
        max_age=14,
        min_participants=2,
        max_participants=20,
        duration_minutes=10,
    )


def _configuration_payload() -> dict[str, list[str] | list[int]]:
    """Build a complete exercise configuration request body."""
    return {
        "equipment_ids": [str(EQUIPMENT_ID)],
        "training_type_ids": [str(TRAINING_TYPE_ID)],
        "segment_ids": [SEGMENT_ID],
    }


def _configuration() -> ExerciseConfiguration:
    """Build resolved catalog rows for an exercise configuration."""
    return ExerciseConfiguration(
        equipment=[
            Equipment(
                id=EQUIPMENT_ID,
                owner_user_id=TRAINER_ID,
                name="Tarcza",
                visibility=CatalogVisibility.LOCAL,
            )
        ],
        training_types=[
            TrainingType(
                id=TRAINING_TYPE_ID,
                owner_user_id=TRAINER_ID,
                name="Techniczny",
                visibility=CatalogVisibility.LOCAL,
            )
        ],
        segments=[TrainingSegment(id=SEGMENT_ID, code="MAIN", name="Część główna")],
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
        equipment=[CatalogReference(id=EQUIPMENT_ID, name="Tarcza")],
        training_types=[CatalogReference(id=TRAINING_TYPE_ID, name="Techniczny")],
        segments=[
            TrainingSegmentResponse(id=SEGMENT_ID, code="MAIN", name="Część główna")
        ],
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
        version_id=None,
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
        version_id=GLOBAL_VERSION_ID,
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
                **_configuration_payload(),
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
                **_configuration_payload(),
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
        **_configuration_payload(),
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
                **_configuration_payload(),
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
                **_configuration_payload(),
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


def test_create_exercise_rejects_duplicate_configuration_ids(
    client, authenticated_trainer
) -> None:
    """Reject duplicate catalog selections before entering the service layer."""
    with patch(
        "app.api.exercises.exercise_service.create_exercise", new=AsyncMock()
    ) as create_exercise:
        response = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Kopnięcie frontalne.",
                "duration_minutes": 10,
                "training_type_ids": [str(TRAINING_TYPE_ID), str(TRAINING_TYPE_ID)],
                "segment_ids": [SEGMENT_ID],
            },
        )

    assert response.status_code == 422
    create_exercise.assert_not_awaited()


def test_create_exercise_hides_unavailable_configuration_entries(
    client, authenticated_trainer
) -> None:
    """Use one validation result for missing, foreign, and non-visible catalog IDs."""
    with patch(
        "app.api.exercises.exercise_service.create_exercise",
        new=AsyncMock(side_effect=exercise_service.InvalidExerciseConfigurationError),
    ):
        response = client.post(
            "/exercises",
            json={
                "name": "Ap chagi",
                "description": "Kopnięcie frontalne.",
                "duration_minutes": 10,
                **_configuration_payload(),
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Exercise configuration contains unavailable catalog entries"
    }


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
                "min_age": 8,
                "max_age": 15,
                "min_participants": 3,
                "max_participants": 18,
                **_configuration_payload(),
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
        min_age=8,
        max_age=15,
        min_participants=3,
        max_participants=18,
        equipment_ids=[EQUIPMENT_ID],
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[SEGMENT_ID],
    )


def test_update_exercise_rejects_non_editable_fields(
    client, authenticated_trainer
) -> None:
    """Reject ownership changes outside SCRUM-133's scope."""
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
                "max_age": 14,
                "min_participants": 2,
                "max_participants": 20,
                "owner_user_id": str(TRAINER_ID),
                **_configuration_payload(),
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
                "min_age": 7,
                "max_age": 14,
                "min_participants": 2,
                "max_participants": 20,
                **_configuration_payload(),
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
    with (
        patch(
            "app.db.exercises.list_available_to_trainer",
            new=AsyncMock(return_value=db_page),
        ) as list_available,
        patch(
            "app.db.exercises.list_configurations",
            new=AsyncMock(
                return_value={
                    PRIVATE_EXERCISE_ID: _configuration(),
                    GLOBAL_EXERCISE_ID: _configuration(),
                }
            ),
        ) as list_configurations,
    ):
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
                equipment=_private_response().equipment,
                training_types=_private_response().training_types,
                segments=_private_response().segments,
            ),
        ],
        total=21,
        page=2,
        page_size=20,
        total_pages=2,
    )
    list_available.assert_awaited_once_with(session, TRAINER_ID, offset=20, limit=20)
    list_configurations.assert_awaited_once_with(session, TRAINER_ID, db_page.items)


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
        equipment_ids=[EQUIPMENT_ID],
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[SEGMENT_ID],
    )
    with (
        patch(
            "app.db.exercises.create_for_trainer",
            return_value=(exercise, trainer_exercise),
        ),
        patch(
            "app.db.exercises.resolve_configuration",
            new=AsyncMock(return_value=_configuration()),
        ),
    ):
        result = asyncio.run(
            exercise_service.create_exercise(session, TRAINER_ID, payload)
        )

    assert result == _private_response()
    assert [item.id for item in trainer_exercise.equipment] == [EQUIPMENT_ID]
    assert [item.id for item in trainer_exercise.training_types] == [TRAINING_TYPE_ID]
    assert [item.id for item in trainer_exercise.segments] == [SEGMENT_ID]
    session.add_all.assert_called_once_with((exercise, trainer_exercise))
    session.commit.assert_awaited_once()


def test_update_exercise_updates_all_its_editable_fields() -> None:
    """Update basic data and trainer configuration of an owned exercise."""
    session = MagicMock()
    session.commit = AsyncMock()
    exercise = _private_exercise()
    trainer_exercise = _private_configuration()
    payload = ExerciseUpdate(
        name="Dollyo chagi",
        description="Kopnięcie okrężne.",
        duration_minutes=15,
        image_url="https://example.com/dollyo-chagi.png",
        min_age=8,
        max_age=15,
        min_participants=3,
        max_participants=18,
        equipment_ids=[EQUIPMENT_ID],
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[SEGMENT_ID],
    )
    with (
        patch(
            "app.db.exercises.get_private_for_trainer",
            new=AsyncMock(return_value=(exercise, trainer_exercise)),
        ) as get_private_for_trainer,
        patch(
            "app.db.exercises.resolve_configuration",
            new=AsyncMock(return_value=_configuration()),
        ),
    ):
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
        min_age=8,
        max_age=15,
        min_participants=3,
        max_participants=18,
    )
    assert result == ExerciseResponse(**expected_data)
    assert exercise.image_url == "https://example.com/dollyo-chagi.png"
    assert (trainer_exercise.min_age, trainer_exercise.max_age) == (8, 15)
    assert (trainer_exercise.min_participants, trainer_exercise.max_participants) == (
        3,
        18,
    )
    assert [item.id for item in trainer_exercise.equipment] == [EQUIPMENT_ID]
    assert [item.id for item in trainer_exercise.training_types] == [TRAINING_TYPE_ID]
    assert [item.id for item in trainer_exercise.segments] == [SEGMENT_ID]
    get_private_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PRIVATE_EXERCISE_ID
    )
    session.commit.assert_awaited_once()


def test_resolve_configuration_rejects_catalog_entries_unavailable_to_trainer() -> None:
    """Reject a configuration with a catalog ID unavailable to its owner."""
    session = AsyncMock()
    configuration = _configuration()
    session.scalars = AsyncMock(
        side_effect=[configuration.equipment, [], configuration.segments]
    )

    result = asyncio.run(
        exercises_db.resolve_configuration(
            session,
            TRAINER_ID,
            equipment_ids=[EQUIPMENT_ID],
            training_type_ids=[TRAINING_TYPE_ID],
            segment_ids=[SEGMENT_ID],
        )
    )

    assert result is None
    assert session.scalars.await_count == 3
    equipment_statement = str(session.scalars.await_args_list[0].args[0]).lower()
    type_statement = str(session.scalars.await_args_list[1].args[0]).lower()
    assert "equipment.visibility" in equipment_statement
    assert "training_types.visibility" in type_statement


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
