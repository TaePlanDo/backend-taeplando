"""Coverage for creation of the genetic algorithm's first generation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services import plan_generation_service
from app.services.plan_generation_candidates_service import PlanExerciseCandidate
from app.services.plan_generation_errors import NoCandidateForSchemaPositionError
from app.services.plan_generation_population_service import (
    PlanExerciseSelection,
    build_initial_population,
)
from app.services.plan_generation_strategies import (
    GenerationContext,
    GenerationSchemaItem,
)


def _candidate(
    identifier: str,
    positions: tuple[int, ...],
    *,
    duration: int = 10,
) -> PlanExerciseCandidate:
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
        segment_ids=(),
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        schema_positions=positions,
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
        schema=(
            GenerationSchemaItem(position=1, segment_id=1, percentage=50),
            GenerationSchemaItem(position=2, segment_id=2, percentage=50),
        ),
        candidates=candidates,
        random_seed=123,
    )


def test_population_contains_complete_plans_and_duration_genes() -> None:
    """Each individual has one valid selection per schema position."""
    first = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", (1,), duration=8)
    second = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", (2,), duration=12)

    population = build_initial_population(_context(first, second), population_size=3)

    assert len(population.individuals) == 3
    for individual in population.individuals:
        assert [selection.schema_position for selection in individual.selections] == [
            1,
            2,
        ]
        assert [selection.candidate for selection in individual.selections] == [
            first,
            second,
        ]
        assert [
            selection.allocated_duration_minutes for selection in individual.selections
        ] == [8, 12]


def test_population_is_deterministic_for_a_generation_job_seed() -> None:
    """A retry of the same job starts with the same first generation."""
    candidates = (
        _candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b", (1, 2)),
        _candidate("3ac590e1-2a46-4cb7-8944-803e364cc46b", (1, 2)),
    )
    context = _context(*candidates)

    assert build_initial_population(context) == build_initial_population(context)


def test_population_rejects_non_positive_duration_candidates() -> None:
    """A malformed candidate cannot be placed into the first generation."""
    invalid = _candidate("4ac590e1-2a46-4cb7-8944-803e364cc46b", (1, 2), duration=0)

    with pytest.raises(NoCandidateForSchemaPositionError, match="1"):
        build_initial_population(_context(invalid))


def test_persisted_selection_uses_its_allocated_duration() -> None:
    """The generated plan snapshots the duration gene, not the source default."""
    candidate = _candidate("5ac590e1-2a46-4cb7-8944-803e364cc46b", (1,), duration=10)
    selection = PlanExerciseSelection(
        schema_position=1,
        candidate=candidate,
        allocated_duration_minutes=7,
    )
    source = SimpleNamespace(
        id=candidate.trainer_exercise_id,
        exercise_id=candidate.exercise_id,
        source_version_id=None,
        exercise=SimpleNamespace(name="Ćwiczenie", description="Opis", image_url=None),
        min_age=7,
        max_age=14,
        min_participants=1,
        max_participants=20,
        duration_minutes=10,
        physical_difficulty=3,
        technical_difficulty=3,
        upper_body_load=3,
        lower_body_load=3,
        core_load=3,
        equipment=[],
        training_types=[],
        segments=[],
        source_version=None,
    )

    plan_exercise = plan_generation_service._plan_exercise(1, selection, source)

    assert plan_exercise.duration_minutes_snapshot == 7
