"""Coverage for synchronous preparation of future plan-generation candidates."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from sqlalchemy.dialects import postgresql

from app.db import exercises as exercises_db
from app.models.enums import EquipmentRequirementMode
from app.schemas.plan_generation import PlanGenerationParameters
from app.services import plan_generation_candidates_service
from app.services.plan_generation_domain import PlanExerciseCandidate
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
EQUIPMENT_ID = UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_EQUIPMENT_ID = UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b")
TRAINING_TYPE_ID = UUID("4ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_TRAINING_TYPE_ID = UUID("5ac590e1-2a46-4cb7-8944-803e364cc46b")
EXERCISE_ID = UUID("fac590e1-2a46-4cb7-8944-803e364cc46b")
EXERCISE_VERSION_ID = UUID("fbc590e1-2a46-4cb7-8944-803e364cc46b")


def _parameters(
    *, training_type_id: UUID | None = TRAINING_TYPE_ID
) -> PlanGenerationParameters:
    return PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[EQUIPMENT_ID],
        training_type_id=training_type_id,
    )


def _group() -> SimpleNamespace:
    return SimpleNamespace(
        id=GROUP_ID,
        min_age=7,
        max_age=14,
        schema_items=[
            SimpleNamespace(position=2, segment_id=2),
            SimpleNamespace(position=1, segment_id=1),
        ],
    )


def _source(
    identifier: UUID,
    *,
    equipment_ids: list[UUID],
    equipment_mode: EquipmentRequirementMode,
    training_type_ids: list[UUID],
    segment_ids: list[int],
    exercise_id: UUID | None = None,
    source_version_id: UUID | None = None,
    duration_minutes: int = 10,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        exercise_id=exercise_id or identifier,
        source_version_id=source_version_id,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        duration_minutes=duration_minutes,
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        equipment_requirement_mode=equipment_mode,
        equipment=[SimpleNamespace(id=item_id) for item_id in equipment_ids],
        training_types=[SimpleNamespace(id=item_id) for item_id in training_type_ids],
        segments=[SimpleNamespace(id=item_id) for item_id in segment_ids],
    )


def test_prepare_candidates_applies_equipment_and_segment_rules() -> None:
    """Keep only active-source candidates usable by this exact request."""

    all_requirement = _source(
        UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[EQUIPMENT_ID],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[2, 1],
        exercise_id=EXERCISE_ID,
        source_version_id=EXERCISE_VERSION_ID,
        duration_minutes=15,
    )
    any_requirement = _source(
        UUID("7ac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[OTHER_EQUIPMENT_ID, EQUIPMENT_ID],
        equipment_mode=EquipmentRequirementMode.ANY,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[2],
    )
    missing_required_equipment = _source(
        UUID("8ac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[OTHER_EQUIPMENT_ID],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[1],
    )
    unmatched_segment = _source(
        UUID("aac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[3],
    )
    session = AsyncMock()
    with (
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.ensure_global_configurations_for_trainer",
            new=AsyncMock(),
        ) as ensure_global_configurations,
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
            new=AsyncMock(
                return_value=[
                    all_requirement,
                    any_requirement,
                    missing_required_equipment,
                    unmatched_segment,
                ]
            ),
        ) as list_candidate_sources,
        patch(
            "app.services.plan_generation_candidates_service.training_plans_db.list_recent_group_exercise_ids",
            new=AsyncMock(return_value=[]),
        ),
    ):
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                session, TRAINER_ID, _group(), _parameters()
            )
        )

    all_candidate = PlanExerciseCandidate(
        trainer_exercise_id=all_requirement.id,
        exercise_id=EXERCISE_ID,
        exercise_version_id=EXERCISE_VERSION_ID,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=15,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=(EQUIPMENT_ID,),
        training_type_ids=(TRAINING_TYPE_ID,),
        segment_ids=(1, 2),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )
    any_candidate = PlanExerciseCandidate(
        trainer_exercise_id=any_requirement.id,
        exercise_id=any_requirement.id,
        exercise_version_id=None,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=10,
        equipment_requirement_mode=EquipmentRequirementMode.ANY,
        equipment_ids=(EQUIPMENT_ID, OTHER_EQUIPMENT_ID),
        training_type_ids=(TRAINING_TYPE_ID,),
        segment_ids=(2,),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )
    assert candidates == (all_candidate, any_candidate)
    ensure_global_configurations.assert_awaited_once_with(session, TRAINER_ID)
    list_candidate_sources.assert_awaited_once_with(
        session,
        TRAINER_ID,
        min_age=7,
        max_age=14,
        participant_count=12,
    )


def test_prepare_candidates_keeps_every_training_type_for_fitness() -> None:
    """A requested type is a fitness preference, never an eligibility filter."""

    matching_type = _source(
        UUID("bac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[1],
    )
    another_type = _source(
        UUID("cac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[OTHER_TRAINING_TYPE_ID],
        segment_ids=[1],
    )
    untyped = _source(
        UUID("dac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[],
        segment_ids=[1],
    )
    with (
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.ensure_global_configurations_for_trainer",
            new=AsyncMock(),
        ),
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
            new=AsyncMock(return_value=[matching_type, another_type, untyped]),
        ),
        patch(
            "app.services.plan_generation_candidates_service.training_plans_db.list_recent_group_exercise_ids",
            new=AsyncMock(return_value=[]),
        ),
    ):
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                AsyncMock(), TRAINER_ID, _group(), _parameters()
            )
        )

    assert [item.trainer_exercise_id for item in candidates] == [
        matching_type.id,
        another_type.id,
        untyped.id,
    ]


def test_prepare_candidates_sets_recent_usage_distances_from_last_plans() -> None:
    """Candidates pick up 1..3 from the group's newest plans, else 4."""
    newest = UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b")
    older = UUID("7ac590e1-2a46-4cb7-8944-803e364cc46b")
    never = UUID("8ac590e1-2a46-4cb7-8944-803e364cc46b")
    sources = [
        _source(
            newest,
            equipment_ids=[],
            equipment_mode=EquipmentRequirementMode.ALL,
            training_type_ids=[],
            segment_ids=[1],
        ),
        _source(
            older,
            equipment_ids=[],
            equipment_mode=EquipmentRequirementMode.ALL,
            training_type_ids=[],
            segment_ids=[1],
        ),
        _source(
            never,
            equipment_ids=[],
            equipment_mode=EquipmentRequirementMode.ALL,
            training_type_ids=[],
            segment_ids=[1],
        ),
    ]

    with (
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.ensure_global_configurations_for_trainer",
            new=AsyncMock(),
        ),
        patch(
            "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
            new=AsyncMock(return_value=sources),
        ),
        patch(
            "app.services.plan_generation_candidates_service.training_plans_db.list_recent_group_exercise_ids",
            new=AsyncMock(return_value=[(newest,), (newest, older)]),
        ),
    ):
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                AsyncMock(), TRAINER_ID, _group(), _parameters()
            )
        )

    by_id = {
        item.trainer_exercise_id: item.recent_usage_distance for item in candidates
    }
    # newest also appears in plan 2; first-seen keeps distance 1.
    assert by_id == {newest: 1, older: 2, never: 4}


def test_list_candidate_sources_accepts_exercises_with_an_age_range_overlap() -> None:
    """A 14–16 exercise remains usable for a 15–17 group."""

    session = AsyncMock()
    result = MagicMock()
    result.unique.return_value = []
    session.scalars = AsyncMock(return_value=result)

    sources = asyncio.run(
        exercises_db.list_candidate_sources(
            session,
            TRAINER_ID,
            min_age=15,
            max_age=17,
            participant_count=12,
        )
    )

    assert sources == []
    statement = session.scalars.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "trainer_exercises.max_age >= 15" in compiled
    assert "trainer_exercises.min_age <= 17" in compiled
    statement = str(statement).lower()
    assert "trainer_exercises.status" in statement
    assert "trainer_exercises.min_age" in statement
    assert "trainer_exercises.max_age" in statement
    assert "trainer_exercises.min_participants" in statement
    assert "trainer_exercises.max_participants" in statement
    assert "exercises.scope" in statement
    assert "order by trainer_exercises.id" in statement
