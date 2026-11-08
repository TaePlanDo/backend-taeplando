"""Coverage for the interchangeable plan-generation algorithm contract."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_candidates_service import PlanExerciseCandidate
from app.services.plan_generation_errors import NoCandidateForSchemaPositionError
from app.services.plan_generation_population_service import build_initial_population
from app.services.plan_generation_strategies import (
    GenerationContext,
    GenerationSchemaItem,
    RandomPlanGenerationStrategy,
)


def _candidate(identifier: str, positions: tuple[int, ...]) -> PlanExerciseCandidate:
    return PlanExerciseCandidate(
        trainer_exercise_id=UUID(identifier),
        exercise_id=UUID(identifier),
        exercise_version_id=None,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=10,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=(),
        training_type_ids=(),
        segment_ids=(),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        schema_positions=positions,
    )


def test_random_strategy_selects_one_eligible_candidate_per_schema_position() -> None:
    """The temporary strategy has a stable random-looking result for one job seed."""

    context = GenerationContext(
        participant_count=12,
        available_equipment_ids=(),
        preferred_training_type_id=None,
        training_group_id=UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b"),
        training_group_name="Grupa",
        group_min_age=7,
        group_max_age=14,
        group_duration_minutes=60,
        deadline_at=datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        schema=(
            GenerationSchemaItem(position=1, segment_id=1, percentage=20),
            GenerationSchemaItem(position=2, segment_id=2, percentage=60),
            GenerationSchemaItem(position=3, segment_id=3, percentage=20),
        ),
        candidates=(
            _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", (1, 2)),
            _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", (2, 3)),
        ),
        random_seed=123,
    )

    strategy = RandomPlanGenerationStrategy()
    population = build_initial_population(context, population_size=3)
    generated = strategy.generate(context, population)

    assert generated == strategy.generate(context, population)
    assert [item.schema_position for item in generated.exercises] == [1, 2, 3]
    assert all(
        item.schema_position in item.candidate.schema_positions
        for item in generated.exercises
    )


def test_random_strategy_rejects_a_schema_position_without_candidates() -> None:
    """The runner can turn an incomplete plan into a typed failed job state."""

    context = GenerationContext(
        participant_count=12,
        available_equipment_ids=(),
        preferred_training_type_id=None,
        training_group_id=UUID("4ac590e1-2a46-4cb7-8944-803e364cc46b"),
        training_group_name="Grupa",
        group_min_age=7,
        group_max_age=14,
        group_duration_minutes=60,
        deadline_at=datetime(2026, 11, 6, 12, 0, tzinfo=UTC),
        schema=(
            GenerationSchemaItem(position=1, segment_id=1, percentage=50),
            GenerationSchemaItem(position=2, segment_id=2, percentage=50),
        ),
        candidates=(_candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b", (1,)),),
        random_seed=1,
    )

    with pytest.raises(NoCandidateForSchemaPositionError, match="2"):
        build_initial_population(context)
