"""Coverage for ranked plan-exercise alternatives API and service."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.enums import EquipmentRequirementMode
from app.models.training import TrainingPlan, TrainingPlanExercise
from app.schemas.exercises import CatalogReference
from app.schemas.training_plans import PlanExerciseAlternative
from app.services import plan_exercise_alternatives_service
from app.services.training_plan_service import (
    PlanExerciseNotFoundError,
    PlanNotFoundError,
)
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
PLAN_ID = UUID("88fa8385-5b07-4346-9ddb-02806890ae4b")
PLAN_EXERCISE_ID = UUID("a8fa8385-5b07-4346-9ddb-02806890ae4b")
OTHER_PLAN_EXERCISE_ID = UUID("aa0a8385-5b07-4346-9ddb-02806890ae4b")
TRAINER_EXERCISE_ID = UUID("b8fa8385-5b07-4346-9ddb-02806890ae4b")
EXERCISE_ID = UUID("c8fa8385-5b07-4346-9ddb-02806890ae4b")
OTHER_EXERCISE_ID = UUID("c9fa8385-5b07-4346-9ddb-02806890ae4b")
THIRD_EXERCISE_ID = UUID("cafa8385-5b07-4346-9ddb-02806890ae4b")
EQUIPMENT_ID = UUID("410327de-b35a-4dcf-8b99-5249e159ce06")
OTHER_EQUIPMENT_ID = UUID("510327de-b35a-4dcf-8b99-5249e159ce06")
TRAINING_TYPE_ID = UUID("2894e3b8-d31a-42a3-89df-fbff1dfb1fb2")
GENERATED_AT = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
SEGMENT_ID = 3
OTHER_SEGMENT_ID = 9


def _orm_plan() -> TrainingPlan:
    plan = TrainingPlan(
        id=PLAN_ID,
        trainer_id=TRAINER_ID,
        training_group_id=GROUP_ID,
        participant_count=12,
        name="Plan treningowy – Młodzież",
        group_name_snapshot="Młodzież",
        group_min_age_snapshot=7,
        group_max_age_snapshot=14,
        training_duration_snapshot=60,
        available_equipment_snapshot=[{"id": str(EQUIPMENT_ID), "name": "Tarcze"}],
        training_types_snapshot=[{"id": str(TRAINING_TYPE_ID), "name": "Kata"}],
        schema_snapshot=[
            {
                "position": 1,
                "segment_id": SEGMENT_ID,
                "code": "MAIN",
                "name": "Ćwiczenia",
                "percentage": 100,
            }
        ],
        generated_at=GENERATED_AT,
    )
    plan.exercises = [
        TrainingPlanExercise(
            id=PLAN_EXERCISE_ID,
            training_plan_id=PLAN_ID,
            trainer_exercise_id=TRAINER_EXERCISE_ID,
            exercise_id=EXERCISE_ID,
            exercise_version_id=None,
            position=1,
            schema_position=1,
            name_snapshot="Ap chagi",
            description_snapshot="Kopnięcie frontalne.",
            image_url_snapshot=None,
            min_age_snapshot=7,
            max_age_snapshot=14,
            min_participants_snapshot=2,
            max_participants_snapshot=20,
            duration_minutes_snapshot=10,
            physical_difficulty_snapshot=3,
            technical_difficulty_snapshot=4,
            upper_body_load_snapshot=2,
            lower_body_load_snapshot=5,
            core_load_snapshot=3,
            equipment_snapshot=[{"id": str(EQUIPMENT_ID), "name": "Tarcze"}],
            training_types_snapshot=[{"id": str(TRAINING_TYPE_ID), "name": "Kata"}],
            segments_snapshot=[{"id": SEGMENT_ID, "code": "MAIN", "name": "Ćwiczenia"}],
        ),
        TrainingPlanExercise(
            id=OTHER_PLAN_EXERCISE_ID,
            training_plan_id=PLAN_ID,
            trainer_exercise_id=uuid4(),
            exercise_id=OTHER_EXERCISE_ID,
            exercise_version_id=None,
            position=2,
            schema_position=1,
            name_snapshot="Dollyo chagi",
            description_snapshot="Kopnięcie okrężne.",
            image_url_snapshot=None,
            min_age_snapshot=7,
            max_age_snapshot=14,
            min_participants_snapshot=2,
            max_participants_snapshot=20,
            duration_minutes_snapshot=8,
            physical_difficulty_snapshot=2,
            technical_difficulty_snapshot=3,
            upper_body_load_snapshot=2,
            lower_body_load_snapshot=4,
            core_load_snapshot=3,
            equipment_snapshot=[],
            training_types_snapshot=[],
            segments_snapshot=[{"id": SEGMENT_ID, "code": "MAIN", "name": "Ćwiczenia"}],
        ),
    ]
    return plan


def _source(
    *,
    exercise_id: UUID,
    trainer_exercise_id: UUID | None = None,
    name: str = "Candidate",
    segment_id: int = SEGMENT_ID,
    equipment_ids: list[UUID] | None = None,
    equipment_mode: EquipmentRequirementMode = EquipmentRequirementMode.ALL,
    physical_difficulty: int = 3,
    technical_difficulty: int = 4,
    duration_minutes: int = 10,
) -> MagicMock:
    source = MagicMock()
    source.id = trainer_exercise_id or uuid4()
    source.exercise_id = exercise_id
    source.source_version_id = None
    source.duration_minutes = duration_minutes
    source.min_age = 7
    source.max_age = 14
    source.min_participants = 2
    source.max_participants = 20
    source.equipment_requirement_mode = equipment_mode
    source.physical_difficulty = physical_difficulty
    source.technical_difficulty = technical_difficulty
    source.upper_body_load = 2
    source.lower_body_load = 5
    source.core_load = 3
    equipment = []
    for item_id in equipment_ids or [EQUIPMENT_ID]:
        item = MagicMock()
        item.id = item_id
        item.name = "Tarcze"
        equipment.append(item)
    source.equipment = equipment
    training_type = MagicMock()
    training_type.id = TRAINING_TYPE_ID
    training_type.name = "Kata"
    source.training_types = [training_type]
    segment = MagicMock()
    segment.id = segment_id
    source.segments = [segment]
    details = MagicMock()
    details.name = name
    details.image_url = f"https://example.com/{name}.png"
    details.animation_url = f"https://example.com/{name}-animation.webp"
    details.image_url_light = f"https://example.com/{name}-light.png"
    details.animation_url_light = f"https://example.com/{name}-animation-light.webp"
    source.source_version = details
    source.exercise = details
    return source


def _alternative(
    *,
    exercise_id: UUID = THIRD_EXERCISE_ID,
    name: str = "Near match",
    similarity_score: float = 0.9,
) -> PlanExerciseAlternative:
    return PlanExerciseAlternative(
        trainer_exercise_id=uuid4(),
        exercise_id=exercise_id,
        name=name,
        image_url=f"https://example.com/{name}.png",
        animation_url=f"https://example.com/{name}-animation.webp",
        image_url_light=f"https://example.com/{name}-light.png",
        animation_url_light=f"https://example.com/{name}-animation-light.webp",
        physical_difficulty=3,
        technical_difficulty=4,
        upper_body_load=2,
        lower_body_load=5,
        core_load=3,
        equipment=[CatalogReference(id=EQUIPMENT_ID, name="Tarcze")],
        training_types=[CatalogReference(id=TRAINING_TYPE_ID, name="Kata")],
        similarity_score=similarity_score,
    )


def test_list_alternatives_requires_authentication(client) -> None:
    response = client.get(
        f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}/alternatives"
    )
    assert response.status_code == 401


def test_list_alternatives_returns_ranked_items(client, authenticated_trainer) -> None:
    items = [
        _alternative(
            exercise_id=THIRD_EXERCISE_ID,
            name="Near match",
            similarity_score=0.9,
        ),
        _alternative(
            exercise_id=uuid4(),
            name="Farther match",
            similarity_score=0.4,
        ),
    ]
    with patch(
        "app.api.training_plans.plan_exercise_alternatives_service.list_alternatives",
        new=AsyncMock(return_value=items),
    ) as list_alternatives:
        response = client.get(
            f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}/alternatives"
            "?limit=5"
        )

    assert response.status_code == 200
    assert response.json() == [item.model_dump(mode="json") for item in items]
    list_alternatives.assert_awaited_once_with(
        ANY, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID, limit=5
    )


@pytest.mark.parametrize(
    ("side_effect", "detail"),
    [
        (PlanNotFoundError, "Plan not found"),
        (PlanExerciseNotFoundError, "Plan exercise not found"),
    ],
)
def test_list_alternatives_returns_not_found(
    client,
    authenticated_trainer,
    side_effect: type[Exception],
    detail: str,
) -> None:
    with patch(
        "app.api.training_plans.plan_exercise_alternatives_service.list_alternatives",
        new=AsyncMock(side_effect=side_effect),
    ):
        response = client.get(
            f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}/alternatives"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": detail}


def test_list_alternatives_rejects_out_of_range_limit(
    client, authenticated_trainer
) -> None:
    response = client.get(
        f"/training-plans/{PLAN_ID}/exercises/{PLAN_EXERCISE_ID}/alternatives?limit=0"
    )
    assert response.status_code == 422


def test_list_alternatives_service_ranks_filters_and_limits() -> None:
    session = AsyncMock()
    plan = _orm_plan()
    near = _source(
        exercise_id=THIRD_EXERCISE_ID,
        name="Near",
        physical_difficulty=3,
        technical_difficulty=4,
    )
    farther = _source(
        exercise_id=uuid4(),
        name="Farther",
        physical_difficulty=1,
        technical_difficulty=1,
        equipment_ids=[EQUIPMENT_ID],
    )
    # Same exercise already on the plan → excluded
    already_on_plan = _source(exercise_id=OTHER_EXERCISE_ID, name="Already")
    # Wrong segment → excluded
    wrong_segment = _source(
        exercise_id=uuid4(), name="Wrong segment", segment_id=OTHER_SEGMENT_ID
    )
    # Equipment outsider with ALL mode → excluded
    equipment_outsider = _source(
        exercise_id=uuid4(),
        name="Needs missing gear",
        equipment_ids=[OTHER_EQUIPMENT_ID],
        equipment_mode=EquipmentRequirementMode.ALL,
    )

    with (
        patch(
            "app.services.plan_exercise_alternatives_service.training_plans_db.get_for_trainer",
            new=AsyncMock(return_value=plan),
        ),
        patch(
            "app.services.plan_exercise_alternatives_service.exercises_db.ensure_global_configurations_for_trainer",
            new=AsyncMock(),
        ),
        patch(
            "app.services.plan_exercise_alternatives_service.exercises_db.list_candidate_sources",
            new=AsyncMock(
                return_value=[
                    farther,
                    near,
                    already_on_plan,
                    wrong_segment,
                    equipment_outsider,
                ]
            ),
        ) as list_candidates,
        patch(
            "app.services.plan_exercise_alternatives_service.exercises_db.list_sources_for_generated_plan",
            new=AsyncMock(return_value={near.id: near, farther.id: farther}),
        ) as list_named,
    ):
        result = asyncio.run(
            plan_exercise_alternatives_service.list_alternatives(
                session, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID, limit=1
            )
        )

    list_candidates.assert_awaited_once_with(
        session,
        TRAINER_ID,
        min_age=7,
        max_age=14,
        participant_count=12,
    )
    assert list_named.await_count == 1
    named_ids = list_named.await_args.args[2]
    assert near.id in named_ids
    assert len(result) == 1
    assert result[0].exercise_id == THIRD_EXERCISE_ID
    assert result[0].name == "Near"
    assert result[0].image_url == "https://example.com/Near.png"
    assert result[0].animation_url == "https://example.com/Near-animation.webp"
    assert result[0].image_url_light == "https://example.com/Near-light.png"
    assert result[0].animation_url_light == (
        "https://example.com/Near-animation-light.webp"
    )
    assert result[0].equipment == [CatalogReference(id=EQUIPMENT_ID, name="Tarcze")]
    assert result[0].similarity_score > 0.5


def test_list_alternatives_service_raises_for_missing_plan() -> None:
    session = AsyncMock()
    with patch(
        "app.services.plan_exercise_alternatives_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(PlanNotFoundError):
            asyncio.run(
                plan_exercise_alternatives_service.list_alternatives(
                    session, TRAINER_ID, PLAN_ID, PLAN_EXERCISE_ID
                )
            )


def test_list_alternatives_service_raises_for_missing_slot() -> None:
    session = AsyncMock()
    with patch(
        "app.services.plan_exercise_alternatives_service.training_plans_db.get_for_trainer",
        new=AsyncMock(return_value=_orm_plan()),
    ):
        with pytest.raises(PlanExerciseNotFoundError):
            asyncio.run(
                plan_exercise_alternatives_service.list_alternatives(
                    session, TRAINER_ID, PLAN_ID, uuid4()
                )
            )
