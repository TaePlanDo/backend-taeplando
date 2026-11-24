"""Coverage for renaming a plan and reordering its exercise slots."""

import asyncio
from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest

from app.models.training import TrainingPlanExercise
from app.services import training_plan_service
from app.services.training_plan_service import (
    PlanNotFoundError,
    PlanStructureInvalidError,
)
from constants import TRAINER_ID
from training_plan_builders import PLAN_ID
from training_plan_builders import (
    orm_plan as _orm_plan,
)
from training_plan_builders import (
    plan_detail as _plan_detail,
)


def test_update_plan_name_returns_updated_detail(client, authenticated_trainer) -> None:
    """PATCH renames the plan and returns the updated detail payload."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_name",
        new=AsyncMock(return_value=detail),
    ) as update_plan_name:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "Nowy plan"},
        )

    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")
    update_plan_name.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PLAN_ID,
        name="Nowy plan",
    )


def test_update_plan_name_returns_not_found(client, authenticated_trainer) -> None:
    """Missing or foreign plans map to 404."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_name",
        new=AsyncMock(side_effect=PlanNotFoundError),
    ):
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "Nowy plan"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


def test_update_plan_name_rejects_blank_name(client, authenticated_trainer) -> None:
    """Whitespace-only names fail request validation before the service runs."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_name",
        new=AsyncMock(),
    ) as update_plan_name:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "   "},
        )

    assert response.status_code == 422
    update_plan_name.assert_not_awaited()


def test_update_plan_name_strips_name(client, authenticated_trainer) -> None:
    """Leading and trailing whitespace are stripped before the service call."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_name",
        new=AsyncMock(return_value=detail),
    ) as update_plan_name:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "  Nowy plan  "},
        )

    assert response.status_code == 200
    update_plan_name.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PLAN_ID,
        name="Nowy plan",
    )


def test_update_plan_name_service_renames() -> None:
    """Service rewrites the plan name without touching exercise positions."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)
    second = next(item for item in plan.exercises if item.position == 2)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ) as get_for_trainer:
        detail = asyncio.run(
            training_plan_service.update_plan_name(
                session,
                TRAINER_ID,
                PLAN_ID,
                name="Plan po edycji",
            )
        )

    get_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PLAN_ID, for_update=True
    )
    assert plan.name == "Plan po edycji"
    assert first.position == 1
    assert second.position == 2
    assert detail.name == "Plan po edycji"
    session.flush.assert_not_awaited()
    session.commit.assert_awaited_once()


def test_update_plan_name_service_raises_for_missing_plan() -> None:
    """Name updates refuse missing or foreign plans without writing."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(
                training_plan_service.update_plan_name(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    name="Plan",
                )
            )

    session.commit.assert_not_called()


def test_update_plan_structure_returns_updated_detail(
    client, authenticated_trainer
) -> None:
    """PATCH structure reorders slots and returns the updated detail payload."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(return_value=detail),
    ) as update_plan_structure:
        response = client.patch(
            f"/training-plans/{PLAN_ID}/structure",
            json={"plan_exercise_ids": [str(detail.exercises[0].id)]},
        )

    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")
    update_plan_structure.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PLAN_ID,
        plan_exercise_ids=[detail.exercises[0].id],
    )


def test_update_plan_structure_returns_not_found(client, authenticated_trainer) -> None:
    """Missing or foreign plans map to 404 for structure updates."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(side_effect=PlanNotFoundError),
    ):
        response = client.patch(
            f"/training-plans/{PLAN_ID}/structure",
            json={"plan_exercise_ids": []},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


def test_update_plan_structure_returns_invalid_order(
    client, authenticated_trainer
) -> None:
    """Non-permutation order lists map to 422."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(side_effect=PlanStructureInvalidError),
    ):
        response = client.patch(
            f"/training-plans/{PLAN_ID}/structure",
            json={"plan_exercise_ids": [str(uuid4())]},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": (
            "Plan exercise order must list each current plan exercise once "
            "and preserve the plan schema_position sequence"
        )
    }


def test_update_plan_structure_service_reorders() -> None:
    """Service rewrites positions while keeping schema_position and name."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    original_name = plan.name
    first = next(item for item in plan.exercises if item.position == 1)
    second = next(item for item in plan.exercises if item.position == 2)
    first_schema = first.schema_position
    second_schema = second.schema_position
    first_duration = first.duration_minutes_snapshot

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ) as get_for_trainer:
        detail = asyncio.run(
            training_plan_service.update_plan_structure(
                session,
                TRAINER_ID,
                PLAN_ID,
                plan_exercise_ids=[second.id, first.id],
            )
        )

    get_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PLAN_ID, for_update=True
    )
    assert plan.name == original_name
    assert second.position == 1
    assert first.position == 2
    assert first.schema_position == first_schema
    assert second.schema_position == second_schema
    assert first.duration_minutes_snapshot == first_duration
    assert [exercise.id for exercise in detail.exercises] == [second.id, first.id]
    assert detail.name == original_name
    assert session.flush.await_count == 1
    session.commit.assert_awaited_once()


def test_update_plan_structure_service_rejects_empty_list() -> None:
    """An empty ID list is invalid when the plan still has exercises."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        with pytest.raises(PlanStructureInvalidError):
            asyncio.run(
                training_plan_service.update_plan_structure(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    plan_exercise_ids=[],
                )
            )

    session.commit.assert_not_called()


def test_update_plan_structure_service_rejects_duplicate_ids() -> None:
    """Repeated slot IDs are not a valid permutation."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        with pytest.raises(PlanStructureInvalidError):
            asyncio.run(
                training_plan_service.update_plan_structure(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    plan_exercise_ids=[first.id, first.id],
                )
            )

    session.commit.assert_not_called()


def test_update_plan_structure_service_rejects_unknown_id() -> None:
    """IDs that are not on the plan are rejected even at the right length."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        with pytest.raises(PlanStructureInvalidError):
            asyncio.run(
                training_plan_service.update_plan_structure(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    plan_exercise_ids=[first.id, uuid4()],
                )
            )

    session.commit.assert_not_called()


def test_update_plan_structure_service_rejects_inconsistent_schema_sequence() -> None:
    """Incoming order must keep the plan's existing schema_position sequence."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)
    second = next(item for item in plan.exercises if item.position == 2)
    second.schema_position = 2

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        with pytest.raises(PlanStructureInvalidError):
            asyncio.run(
                training_plan_service.update_plan_structure(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    plan_exercise_ids=[second.id, first.id],
                )
            )

    session.commit.assert_not_called()
    assert first.position == 1
    assert second.position == 2


def _extra_plan_exercise(
    *,
    template: TrainingPlanExercise,
    position: int,
    schema_position: int,
    name: str,
) -> TrainingPlanExercise:
    return TrainingPlanExercise(
        id=uuid4(),
        training_plan_id=PLAN_ID,
        trainer_exercise_id=template.trainer_exercise_id,
        exercise_id=template.exercise_id,
        exercise_version_id=None,
        position=position,
        schema_position=schema_position,
        name_snapshot=name,
        description_snapshot="",
        image_url_snapshot=None,
        animation_url_snapshot=None,
        image_url_light_snapshot=None,
        animation_url_light_snapshot=None,
        min_age_snapshot=7,
        max_age_snapshot=14,
        min_participants_snapshot=2,
        max_participants_snapshot=20,
        duration_minutes_snapshot=5,
        physical_difficulty_snapshot=3,
        technical_difficulty_snapshot=3,
        upper_body_load_snapshot=2,
        lower_body_load_snapshot=3,
        core_load_snapshot=3,
        equipment_snapshot=[],
        training_types_snapshot=[],
        segments_snapshot=[{"id": 3, "code": "MAIN", "name": "Ćwiczenia"}],
    )


def test_update_plan_structure_service_allows_reorder_within_segments() -> None:
    """Slots may move freely as long as the schema_position sequence stays identical."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)
    second = next(item for item in plan.exercises if item.position == 2)
    third = _extra_plan_exercise(
        template=first,
        position=3,
        schema_position=2,
        name="Segment two",
    )
    plan.exercises.append(third)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        detail = asyncio.run(
            training_plan_service.update_plan_structure(
                session,
                TRAINER_ID,
                PLAN_ID,
                plan_exercise_ids=[second.id, first.id, third.id],
            )
        )

    assert [exercise.id for exercise in detail.exercises] == [
        second.id,
        first.id,
        third.id,
    ]
    assert [exercise.schema_position for exercise in detail.exercises] == [1, 1, 2]
    session.commit.assert_awaited_once()


def test_update_plan_structure_service_allows_any_existing_schema_layout() -> None:
    """Schema order need not be sorted; only consistency with the plan matters."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)
    second = next(item for item in plan.exercises if item.position == 2)
    first.schema_position = 2
    second.schema_position = 1
    third = _extra_plan_exercise(
        template=first,
        position=3,
        schema_position=1,
        name="Same segment as second",
    )
    plan.exercises.append(third)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        detail = asyncio.run(
            training_plan_service.update_plan_structure(
                session,
                TRAINER_ID,
                PLAN_ID,
                plan_exercise_ids=[first.id, third.id, second.id],
            )
        )

    assert [exercise.id for exercise in detail.exercises] == [
        first.id,
        third.id,
        second.id,
    ]
    assert [exercise.schema_position for exercise in detail.exercises] == [2, 1, 1]
    session.commit.assert_awaited_once()


def test_update_plan_structure_service_raises_for_missing_plan() -> None:
    """Structure updates refuse missing or foreign plans without writing."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(
                training_plan_service.update_plan_structure(
                    session,
                    TRAINER_ID,
                    PLAN_ID,
                    plan_exercise_ids=[],
                )
            )

    session.commit.assert_not_called()
