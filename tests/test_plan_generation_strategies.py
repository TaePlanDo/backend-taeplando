"""Coverage for the interchangeable one-segment generation strategy contract."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
    PlanIndividual,
)
from app.services.plan_generation_population_service import build_initial_population
from app.services.plan_generation_strategies import (
    GeneticPlanGenerationStrategy,
    RandomPlanGenerationStrategy,
)


def _candidate(identifier: str) -> PlanExerciseCandidate:
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
        segment_ids=(2,),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        recent_usage_distance=4,
    )


def test_genetic_strategy_delegates_to_evolve_with_injected_best() -> None:
    """Genetic strategy injects BestSoFar and forwards it to evolve."""
    context = MagicMock()
    population = MagicMock()
    best = BestSoFar()
    generated = PlanIndividual(selections=())

    with patch(
        "app.services.plan_generation_strategies.evolve",
        return_value=generated,
    ) as evolve:
        result = GeneticPlanGenerationStrategy(best).generate(context, population)

    assert result is generated
    evolve.assert_called_once_with(context, population, best=best)


def test_random_strategy_selects_a_stable_segment() -> None:
    """The random strategy has a stable result for one job-segment seed."""
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
        segment=GenerationSchemaItem(position=2, segment_id=2, percentage=60),
        segment_duration_minutes=36,
        candidates=(
            _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b"),
            _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b"),
        ),
        random_seed=123,
    )

    strategy = RandomPlanGenerationStrategy(BestSoFar())
    population = build_initial_population(context, population_size=3)
    generated = strategy.generate(context, population)

    assert generated == strategy.generate(context, population)
    assert {item.schema_position for item in generated.selections} == {2}
    assert all(
        item.allocated_duration_minutes == item.candidate.default_duration_minutes
        for item in generated.selections
    )
    assert all(2 in item.candidate.segment_ids for item in generated.selections)
