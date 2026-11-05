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
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
EQUIPMENT_ID = UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_EQUIPMENT_ID = UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b")
TRAINING_TYPE_ID = UUID("4ac590e1-2a46-4cb7-8944-803e364cc46b")
OTHER_TRAINING_TYPE_ID = UUID("5ac590e1-2a46-4cb7-8944-803e364cc46b")


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
        min_age=7,
        max_age=14,
        schema_items=[
            SimpleNamespace(position=1, segment_id=1),
            SimpleNamespace(position=2, segment_id=2),
        ],
    )


def _source(
    identifier: UUID,
    *,
    equipment_ids: list[UUID],
    equipment_mode: EquipmentRequirementMode,
    training_type_ids: list[UUID],
    segment_ids: list[int],
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identifier,
        exercise_id=identifier,
        source_version_id=None,
        duration_minutes=10,
        equipment_requirement_mode=equipment_mode,
        equipment=[SimpleNamespace(id=item_id) for item_id in equipment_ids],
        training_types=[SimpleNamespace(id=item_id) for item_id in training_type_ids],
        segments=[SimpleNamespace(id=item_id) for item_id in segment_ids],
    )


def test_prepare_candidates_applies_equipment_type_and_segment_rules() -> None:
    """Keep only active-source candidates usable by this exact request."""

    all_requirement = _source(
        UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[EQUIPMENT_ID],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[TRAINING_TYPE_ID],
        segment_ids=[1],
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
    wrong_type = _source(
        UUID("9ac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[OTHER_TRAINING_TYPE_ID],
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
    with patch(
        "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
        new=AsyncMock(
            return_value=[
                all_requirement,
                any_requirement,
                missing_required_equipment,
                wrong_type,
                unmatched_segment,
            ]
        ),
    ) as list_candidate_sources:
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                session, TRAINER_ID, _group(), _parameters()
            )
        )

    assert [
        (item.trainer_exercise_id, item.schema_positions) for item in candidates
    ] == [
        (all_requirement.id, (1,)),
        (any_requirement.id, (2,)),
    ]
    list_candidate_sources.assert_awaited_once_with(
        session,
        TRAINER_ID,
        min_age=7,
        max_age=14,
        participant_count=12,
    )


def test_prepare_candidates_skips_type_filter_for_automatic_selection() -> None:
    """An omitted training type leaves all configured types eligible."""

    source = _source(
        UUID("bac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[OTHER_TRAINING_TYPE_ID],
        segment_ids=[1],
    )
    with patch(
        "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
        new=AsyncMock(return_value=[source]),
    ):
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                AsyncMock(), TRAINER_ID, _group(), _parameters(training_type_id=None)
            )
        )

    assert [item.trainer_exercise_id for item in candidates] == [source.id]


def test_prepare_candidates_treats_an_untyped_exercise_as_universal() -> None:
    """An exercise without types remains eligible for a selected training type."""

    source = _source(
        UUID("cac590e1-2a46-4cb7-8944-803e364cc46b"),
        equipment_ids=[],
        equipment_mode=EquipmentRequirementMode.ALL,
        training_type_ids=[],
        segment_ids=[1],
    )
    with patch(
        "app.services.plan_generation_candidates_service.exercises_db.list_candidate_sources",
        new=AsyncMock(return_value=[source]),
    ):
        candidates = asyncio.run(
            plan_generation_candidates_service.prepare_candidates(
                AsyncMock(), TRAINER_ID, _group(), _parameters()
            )
        )

    assert [item.trainer_exercise_id for item in candidates] == [source.id]


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
