"""Coverage for replacing and deleting exercises inside a saved plan."""

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.db import training_plans as training_plans_db
from app.models.training import TrainingPlanExercise
from app.services import training_plan_service
from app.services.training_plan_service import PlanNotFoundError
from constants import TRAINER_ID
from training_plan_builders import (
    EXERCISE_ID,
    EXERCISE_VERSION_ID,
    PLAN_EXERCISE_ID,
    PLAN_ID,
    TRAINER_EXERCISE_ID,
)
from training_plan_builders import (
    orm_plan as _orm_plan,
)
from training_plan_builders import (
    plan_detail as _plan_detail,
)


def test_get_for_trainer_for_update_locks_the_plan_row() -> None:
    """Mutation lookups serialize concurrent writers with FOR UPDATE."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = _orm_plan()
    session.execute = AsyncMock(return_value=result)

    asyncio.run(
        training_plans_db.get_for_trainer(session, TRAINER_ID, PLAN_ID, for_update=True)
    )

    statement = str(session.execute.await_args.args[0]).lower()
    assert "for update" in statement


def test_replace_plan_exercise_returns_updated_slot(
    client, authenticated_trainer
) -> None:
    """PUT replaces one slot and returns the updated plan-exercise payload."""
    updated = _plan_detail().exercises[0]
    with patch(
        "app.api.training_plans.training_plan_service.replace_plan_exercise",
        new=AsyncMock(return_value=updated),
    ) as replace_plan_exercise:
        response = client.put(
            f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}",
            json={"exercise_id": str(EXERCISE_ID)},
        )

    assert response.status_code == 200
    assert response.json() == updated.model_dump(mode="json")
    replace_plan_exercise.assert_awaited_once_with(
        ANY, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID, EXERCISE_ID
    )


@pytest.mark.parametrize(
    ("side_effect", "detail"),
    [
        (PlanNotFoundError, "Plan not found"),
        (training_plan_service.PlanExerciseNotFoundError, "Plan exercise not found"),
        (training_plan_service.PlanExerciseUnavailableError, "Exercise not found"),
    ],
)
def test_replace_plan_exercise_returns_not_found(
    client, authenticated_trainer, side_effect: type[Exception], detail: str
) -> None:
    """Missing plan, slot, or unavailable exercise all map to 404."""
    with patch(
        "app.api.training_plans.training_plan_service.replace_plan_exercise",
        new=AsyncMock(side_effect=side_effect),
    ):
        response = client.put(
            f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}",
            json={"exercise_id": str(EXERCISE_ID)},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_delete_plan_exercise_returns_no_content(client, authenticated_trainer) -> None:
    """DELETE removes one slot with an empty 204 body."""
    with patch(
        "app.api.training_plans.training_plan_service.delete_plan_exercise",
        new=AsyncMock(),
    ) as delete_plan_exercise:
        response = client.delete(
            f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}"
        )

    assert response.status_code == 204
    assert response.content == b""
    delete_plan_exercise.assert_awaited_once_with(
        ANY, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID
    )


@pytest.mark.parametrize(
    ("side_effect", "detail"),
    [
        (PlanNotFoundError, "Plan not found"),
        (training_plan_service.PlanExerciseNotFoundError, "Plan exercise not found"),
    ],
)
def test_delete_plan_exercise_returns_not_found(
    client, authenticated_trainer, side_effect: type[Exception], detail: str
) -> None:
    """Missing plan or slot map to 404 without writing."""
    with patch(
        "app.api.training_plans.training_plan_service.delete_plan_exercise",
        new=AsyncMock(side_effect=side_effect),
    ):
        response = client.delete(f"/training-plans/{PLAN_ID}/exercises/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_replace_plan_exercise_service_keeps_order_and_duration() -> None:
    """Replace overwrites identity/snapshots but keeps position and duration."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    slot = next(item for item in plan.exercises if item.id == PLAN_EXERCISE_ID)
    original_position = slot.position
    original_schema_position = slot.schema_position
    original_duration = slot.duration_minutes_snapshot
    replacement_exercise_id = uuid4()
    source = MagicMock()
    source.id = uuid4()
    source.exercise_id = replacement_exercise_id
    source.source_version_id = uuid4()

    with (
        patch(
            "app.services.training_plan_service.training_plans_db.get_for_trainer",
            new=AsyncMock(return_value=plan),
        ) as get_for_trainer,
        patch(
            "app.services.training_plan_service._resolve_active_source",
            new=AsyncMock(return_value=source),
        ),
        patch(
            "app.services.training_plan_service.fill_plan_exercise_from_source",
        ) as fill_snapshots,
    ):
        result = asyncio.run(
            training_plan_service.replace_plan_exercise(
                session,
                TRAINER_ID,
                PLAN_ID,
                PLAN_EXERCISE_ID,
                replacement_exercise_id,
            )
        )

    get_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PLAN_ID, for_update=True
    )
    fill_snapshots.assert_called_once_with(
        slot, source, duration_minutes=original_duration
    )
    assert slot.position == original_position
    assert slot.schema_position == original_schema_position
    assert result.position == original_position
    session.commit.assert_awaited_once()


def test_replace_plan_exercise_service_raises_for_missing_slot() -> None:
    """Replace refuses unknown slots on an owned plan."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=_orm_plan(with_exercises=True)),
    ):
        with pytest.raises(training_plan_service.PlanExerciseNotFoundError):
            asyncio.run(
                training_plan_service.replace_plan_exercise(
                    session, TRAINER_ID, PLAN_ID, uuid4(), EXERCISE_ID
                )
            )

    session.commit.assert_not_called()


def _third_slot(*, position: int = 3) -> TrainingPlanExercise:
    return TrainingPlanExercise(
        id=uuid4(),
        training_plan_id=PLAN_ID,
        trainer_exercise_id=TRAINER_EXERCISE_ID,
        exercise_id=EXERCISE_ID,
        exercise_version_id=None,
        position=position,
        schema_position=2,
        name_snapshot="Yop chagi",
        description_snapshot="Kopnięcie boczne.",
        image_url_snapshot=None,
        animation_url_snapshot=None,
        image_url_light_snapshot=None,
        animation_url_light_snapshot=None,
        min_age_snapshot=7,
        max_age_snapshot=14,
        min_participants_snapshot=2,
        max_participants_snapshot=20,
        duration_minutes_snapshot=12,
        physical_difficulty_snapshot=3,
        technical_difficulty_snapshot=3,
        upper_body_load_snapshot=2,
        lower_body_load_snapshot=4,
        core_load_snapshot=3,
        equipment_snapshot=[],
        training_types_snapshot=[],
        segments_snapshot=[{"id": 3, "code": "MAIN", "name": "Ćwiczenia"}],
    )


def test_delete_plan_exercise_service_renumbers_remaining_positions() -> None:
    """Deleting a middle slot rewrites positions to 1..n without changing times."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    first = next(item for item in plan.exercises if item.position == 1)
    middle_id = PLAN_EXERCISE_ID
    last = _third_slot()
    plan.exercises.append(last)
    middle = next(item for item in plan.exercises if item.id == middle_id)
    first_duration = first.duration_minutes_snapshot
    last_duration = last.duration_minutes_snapshot
    assert middle.position == 2

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ) as get_for_trainer:
        asyncio.run(
            training_plan_service.delete_plan_exercise(
                session, TRAINER_ID, PLAN_ID, middle_id
            )
        )

    get_for_trainer.assert_awaited_once_with(
        session, TRAINER_ID, PLAN_ID, for_update=True
    )
    assert middle not in plan.exercises
    assert [
        (exercise.id, exercise.position)
        for exercise in sorted(plan.exercises, key=lambda item: item.position)
    ] == [(first.id, 1), (last.id, 2)]
    assert first.duration_minutes_snapshot == first_duration
    assert last.duration_minutes_snapshot == last_duration
    assert session.flush.await_count == 2
    session.commit.assert_awaited_once()


def test_delete_first_position_parks_above_remaining_max() -> None:
    """Deleting position 1 parks above the still-held high positions."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    last = _third_slot()
    plan.exercises.append(last)
    first = next(item for item in plan.exercises if item.position == 1)
    remaining_max_after_delete = max(
        item.position for item in plan.exercises if item.id != first.id
    )
    flush_snapshots: list[list[int]] = []

    async def track_flush() -> None:
        flush_snapshots.append(sorted(exercise.position for exercise in plan.exercises))

    session.flush = AsyncMock(side_effect=track_flush)

    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=plan),
    ):
        asyncio.run(
            training_plan_service.delete_plan_exercise(
                session, TRAINER_ID, PLAN_ID, first.id
            )
        )

    assert len(flush_snapshots) == 2
    assert flush_snapshots[0] == [2, 3]
    assert all(position > remaining_max_after_delete for position in flush_snapshots[1])
    assert [
        exercise.position
        for exercise in sorted(plan.exercises, key=lambda item: item.position)
    ] == [1, 2]
    session.commit.assert_awaited_once()


def test_delete_plan_exercise_service_raises_for_missing_plan() -> None:
    """Delete refuses missing or foreign plans without writing."""
    session = AsyncMock()
    with patch(
        "app.services.training_plan_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(
                training_plan_service.delete_plan_exercise(
                    session, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID
                )
            )

    session.commit.assert_not_called()


def test_plan_mutations_serialize_with_for_update() -> None:
    """Replace and delete both lock the plan row before mutating slots."""
    session = AsyncMock()
    plan = _orm_plan(with_exercises=True)
    source = MagicMock()
    source.id = TRAINER_EXERCISE_ID
    source.exercise_id = EXERCISE_ID
    source.source_version_id = EXERCISE_VERSION_ID

    with (
        patch(
            "app.services.training_plan_service.training_plans_db.get_for_trainer",
            new=AsyncMock(return_value=plan),
        ) as get_for_trainer,
        patch(
            "app.services.training_plan_service._resolve_active_source",
            new=AsyncMock(return_value=source),
        ),
        patch("app.services.training_plan_service.fill_plan_exercise_from_source"),
    ):
        asyncio.run(
            training_plan_service.replace_plan_exercise(
                session, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID, EXERCISE_ID
            )
        )
        asyncio.run(
            training_plan_service.delete_plan_exercise(
                session, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID
            )
        )

    assert get_for_trainer.await_args_list == [
        ((session, TRAINER_ID, PLAN_ID), {"for_update": True}),
        ((session, TRAINER_ID, PLAN_ID), {"for_update": True}),
    ]
