"""Coverage for creation of one segment's genetic first generation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    PlanExerciseCandidate,
)
from app.services.plan_generation_errors import (
    NoCandidateForSchemaPositionError,
    NoDurationForSchemaPositionError,
)
from app.services.plan_generation_population_service import (
    allocate_segment_durations,
    build_initial_population,
)


def _candidate(identifier: str, *, duration: int = 10) -> PlanExerciseCandidate:
    return PlanExerciseCandidate(
        trainer_exercise_id=UUID(identifier),
        exercise_id=UUID(identifier),
        exercise_version_id=None,
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        default_duration_minutes=duration,
        equipment_requirement_mode=EquipmentRequirementMode.ALL,
        equipment_ids=(),
        training_type_ids=(),
        segment_ids=(1,),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
    )


def _context(*candidates: PlanExerciseCandidate) -> GenerationContext:
    return GenerationContext(
        participant_count=12,
        available_equipment_ids=(),
        preferred_training_type_id=None,
        training_group_id=UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b"),
        training_group_name="Grupa",
        group_min_age=7,
        group_max_age=14,
        group_duration_minutes=60,
        deadline_at=datetime(2026, 11, 7, 12, 0, tzinfo=UTC),
        segment=GenerationSchemaItem(position=1, segment_id=1, percentage=50),
        segment_duration_minutes=30,
        candidates=candidates,
        random_seed=123,
    )


def test_population_contains_only_one_segment_and_duration_genes() -> None:
    """Each individual fills exactly the segment owned by its context."""
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=8)

    population = build_initial_population(_context(candidate), population_size=3)

    assert len(population.individuals) == 3
    for individual in population.individuals:
        assert [selection.schema_position for selection in individual.selections] == [1]
        assert [selection.candidate for selection in individual.selections] == [
            candidate
        ]
        assert [
            selection.allocated_duration_minutes for selection in individual.selections
        ] == [30]


def test_population_greedily_fills_its_segment() -> None:
    """Longer fitting candidates are selected before a duration gene is extended."""
    first = _candidate("5ac590e1-2a46-4cb7-8944-803e364cc46b", duration=8)
    second = _candidate("6ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)

    individual = build_initial_population(
        _context(first, second), population_size=1
    ).individuals[0]

    assert [
        selection.allocated_duration_minutes for selection in individual.selections
    ] == [
        10,
        20,
    ]


def test_allocate_segment_durations_preserves_the_whole_plan_duration() -> None:
    """Rounding happens once before the independent segment runs begin."""
    schema = (
        GenerationSchemaItem(position=1, segment_id=1, percentage=Decimal("33.33")),
        GenerationSchemaItem(position=2, segment_id=2, percentage=Decimal("33.33")),
        GenerationSchemaItem(position=3, segment_id=3, percentage=Decimal("33.34")),
    )

    assert allocate_segment_durations(7, schema) == {1: 2, 2: 2, 3: 3}


def test_population_is_deterministic_for_one_segment_context() -> None:
    """A retry of the same job and segment starts with the same population."""
    candidates = (
        _candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b"),
        _candidate("3ac590e1-2a46-4cb7-8944-803e364cc46b"),
    )
    context = _context(*candidates)

    assert build_initial_population(context) == build_initial_population(context)


def test_population_rejects_a_segment_without_a_whole_minute() -> None:
    """Every independently generated segment still needs one whole minute."""
    schema = (
        GenerationSchemaItem(position=1, segment_id=1, percentage=50),
        GenerationSchemaItem(position=2, segment_id=2, percentage=50),
    )

    with pytest.raises(NoDurationForSchemaPositionError, match="2"):
        allocate_segment_durations(1, schema)


def test_population_rejects_non_positive_duration_candidates() -> None:
    """A malformed candidate cannot enter a segment's first generation."""
    invalid = _candidate("4ac590e1-2a46-4cb7-8944-803e364cc46b", duration=0)

    with pytest.raises(NoCandidateForSchemaPositionError, match="1"):
        build_initial_population(_context(invalid))
