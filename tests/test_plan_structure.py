"""Coverage for renaming a plan and reordering its exercise slots."""

import asyncio
from unittest.mock import ANY, AsyncMock, patch
from uuid import uuid4

import pytest

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


def test_update_plan_structure_returns_updated_detail(
    client, authenticated_trainer
) -> None:
    """PATCH renames the plan and returns the updated detail payload."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(return_value=detail),
    ) as update_plan_structure:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={
                "name": "Nowy plan",
                "plan_exercise_ids": [str(detail.exercises[0].id)],
            },
        )

    assert response.status_code == 200
    assert response.json() == detail.model_dump(mode="json")
    update_plan_structure.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PLAN_ID,
        name="Nowy plan",
        plan_exercise_ids=[detail.exercises[0].id],
    )


def test_update_plan_structure_returns_not_found(client, authenticated_trainer) -> None:
    """Missing or foreign plans map to 404."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(side_effect=PlanNotFoundError),
    ):
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "Nowy plan", "plan_exercise_ids": []},
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
            f"/training-plans/{PLAN_ID}",
            json={"name": "Nowy plan", "plan_exercise_ids": [str(uuid4())]},
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Plan exercise order must list each current plan exercise once"
    }


def test_update_plan_structure_rejects_blank_name(
    client, authenticated_trainer
) -> None:
    """Whitespace-only names fail request validation before the service runs."""
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(),
    ) as update_plan_structure:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={"name": "   ", "plan_exercise_ids": []},
        )

    assert response.status_code == 422
    update_plan_structure.assert_not_awaited()


def test_update_plan_structure_strips_name(client, authenticated_trainer) -> None:
    """Leading and trailing whitespace are stripped before the service call."""
    detail = _plan_detail()
    with patch(
        "app.api.training_plans.training_plan_service.update_plan_structure",
        new=AsyncMock(return_value=detail),
    ) as update_plan_structure:
        response = client.patch(
            f"/training-plans/{PLAN_ID}",
            json={
                "name": "  Nowy plan  ",
                "plan_exercise_ids": [str(detail.exercises[0].id)],
            },
        )

    assert response.status_code == 200
    update_plan_structure.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PLAN_ID,
        name="Nowy plan",
        plan_exercise_ids=[detail.exercises[0].id],
    )


def test_update_plan_structure_service_renames_and_reorders() -> None:
    """Service rewrites name and positions while keeping schema_position."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
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
                name="Plan po edycji",
                plan_exercise_ids=[second.id, first.id],
            )
        )

    get_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PLAN_ID, for_update=True
    )
    assert plan.name == "Plan po edycji"
    assert second.position == 1
    assert first.position == 2
    assert first.schema_position == first_schema
    assert second.schema_position == second_schema
    assert first.duration_minutes_snapshot == first_duration
    assert [exercise.id for exercise in detail.exercises] == [second.id, first.id]
    assert detail.name == "Plan po edycji"
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
                    name="Plan",
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
                    name="Plan",
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
                    name="Plan",
                    plan_exercise_ids=[first.id, uuid4()],
                )
            )

    session.commit.assert_not_called()


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
                    name="Plan",
                    plan_exercise_ids=[],
                )
            )

    session.commit.assert_not_called()
