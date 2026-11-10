"""Coverage for DEAP evolution operators and BestSoFar publishing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    InitialPopulation,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_errors import NoValidPlanError
from app.services.plan_generation_evolution import (
    evolve,
    from_deap,
    is_structurally_valid,
    temporary_fitness,
    to_deap,
    _crossover,
    _mutate,
)
from app.services.plan_generation_population_service import build_initial_population


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


def _context(
    *candidates: PlanExerciseCandidate,
    seed: int = 123,
    deadline: datetime | None = None,
) -> GenerationContext:
    return GenerationContext(
        participant_count=12,
        available_equipment_ids=(),
        preferred_training_type_id=None,
        training_group_id=UUID("6ac590e1-2a46-4cb7-8944-803e364cc46b"),
        training_group_name="Grupa",
        group_min_age=7,
        group_max_age=14,
        group_duration_minutes=60,
        deadline_at=deadline
        or (datetime.now(UTC) + timedelta(seconds=30)),
        segment=GenerationSchemaItem(position=1, segment_id=1, percentage=50),
        segment_duration_minutes=30,
        candidates=candidates,
        random_seed=seed,
    )


def test_temporary_fitness_is_deterministic_for_the_same_individual() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    context = _context(candidate, seed=99)
    individual = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(
                    schema_position=1,
                    candidate=candidate,
                    allocated_duration_minutes=10,
                ),
            )
        ),
        context_seed=99,
    )

    assert temporary_fitness(individual, context=context) == temporary_fitness(
        individual, context=context
    )
    assert 0 <= temporary_fitness(individual, context=context)[0] <= 100


def test_evolution_is_deterministic_for_one_seed() -> None:
    context = _context(
        _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b"),
        _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b"),
        seed=7,
    )
    population = build_initial_population(context, population_size=4)

    assert evolve(context, population, best=BestSoFar()) == evolve(
        context, population, best=BestSoFar()
    )


def test_crossover_preserves_gene_durations() -> None:
    first_candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=8)
    second_candidate = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", duration=12)
    parent_a = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(1, first_candidate, 8),
                PlanExerciseSelection(1, second_candidate, 12),
            )
        ),
        1,
    )
    parent_b = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(1, second_candidate, 12),
                PlanExerciseSelection(1, first_candidate, 8),
            )
        ),
        1,
    )
    from random import Random

    _crossover(parent_a, parent_b, random=Random(0))

    assert all(gene.allocated_duration_minutes in {8, 12} for gene in parent_a)
    assert all(gene.allocated_duration_minutes in {8, 12} for gene in parent_b)


def test_mutation_can_change_allocated_duration() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    individual = to_deap(
        PlanIndividual(
            selections=(PlanExerciseSelection(1, candidate, 10),)
        ),
        1,
    )

    class DurationMutationRandom:
        def randint(self, low: int, high: int) -> int:
            if (low, high) == (0, 2):
                return 0
            return 3

        def randrange(self, stop: int) -> int:
            return 0

        def choice(self, sequence):  # noqa: ANN001
            return 1

    _mutate(individual, candidates=(candidate,), random=DurationMutationRandom())

    assert individual[0].allocated_duration_minutes == 13


def test_evolve_publishes_best_so_far() -> None:
    context = _context(
        _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b"),
        _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b"),
    )
    best = BestSoFar()
    best.set_required_positions((1,))
    population = build_initial_population(context, population_size=4)

    generated = evolve(context, population, best=best)

    assert best.snapshot() == generated
    assert is_structurally_valid(context, generated)


def test_best_so_far_requires_every_segment() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    best = BestSoFar()
    best.set_required_positions((1, 2))
    best.publish(
        1,
        PlanIndividual(
            selections=(PlanExerciseSelection(1, candidate, 10),)
        ),
    )

    assert best.snapshot() is None


def test_evolve_rejects_an_empty_population() -> None:
    context = _context(_candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b"))

    with pytest.raises(NoValidPlanError):
        evolve(context, InitialPopulation(individuals=()), best=BestSoFar())


def test_from_deap_round_trips_domain_individual() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    original = PlanIndividual(
        selections=(PlanExerciseSelection(1, candidate, 10),)
    )

    assert from_deap(to_deap(original, 5)) == original
