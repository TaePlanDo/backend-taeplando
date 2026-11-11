"""Coverage for DEAP evolution operators and BestSoFar publishing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.models.enums import EquipmentRequirementMode
from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    InitialPopulation,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import NoValidPlanError
from app.services.plan_generation_evolution import (
    _crossover,
    _evaluate,
    _mutate,
    evolve,
    from_deap,
    is_structurally_valid,
    to_deap,
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
        recent_usage_distance=4,
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
        deadline_at=deadline or (datetime.now(UTC) + timedelta(seconds=30)),
        segment=GenerationSchemaItem(position=1, segment_id=1, percentage=50),
        segment_duration_minutes=30,
        candidates=candidates,
        random_seed=seed,
    )


def test_evaluate_uses_plan_fitness_and_prefers_on_budget_duration() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    context = _context(candidate)
    on_budget = to_deap(
        PlanIndividual(selections=(PlanExerciseSelection(1, candidate, 30),)),
        context_seed=1,
    )
    short = to_deap(
        PlanIndividual(selections=(PlanExerciseSelection(1, candidate, 10),)),
        context_seed=1,
    )

    on_budget_score = _evaluate(on_budget, context=context)[0]
    short_score = _evaluate(short, context=context)[0]

    assert 0.0 <= on_budget_score <= 1.0
    assert on_budget_score > short_score
    assert _evaluate(on_budget, context=context) == _evaluate(
        on_budget, context=context
    )


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


def test_crossover_keeps_prefix_and_unused_donor_suffix() -> None:
    first_candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=8)
    second_candidate = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", duration=12)
    third_candidate = _candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    fourth_candidate = _candidate("3ac590e1-2a46-4cb7-8944-803e364cc46b", duration=14)
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
                PlanExerciseSelection(1, third_candidate, 10),
                PlanExerciseSelection(1, fourth_candidate, 14),
            )
        ),
        1,
    )
    from random import Random

    _crossover(parent_a, parent_b, random=Random(0))

    # point=1: prefix + unused donor suffix only (no donor-prefix backfill).
    assert [gene.allocated_duration_minutes for gene in parent_a] == [8, 14]
    assert [gene.allocated_duration_minutes for gene in parent_b] == [10, 12]
    assert _unique_exercise_ids(parent_a)
    assert _unique_exercise_ids(parent_b)


def test_crossover_does_not_pull_from_donor_prefix() -> None:
    kept = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=8)
    filler = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", duration=12)
    extra = _candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    parent_a = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(1, kept, 8),
                PlanExerciseSelection(1, extra, 10),
            )
        ),
        1,
    )
    parent_b = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(1, filler, 12),
                PlanExerciseSelection(1, kept, 8),
            )
        ),
        1,
    )
    from random import Random

    _crossover(parent_a, parent_b, random=Random(0))

    # point=1: A keeps [kept]; B suffix is kept (duplicate) → no suffix add.
    assert [gene.candidate.trainer_exercise_id for gene in parent_a] == [
        kept.trainer_exercise_id,
    ]
    assert _unique_exercise_ids(parent_a)
    assert _unique_exercise_ids(parent_b)


def test_crossover_skips_donor_genes_already_in_prefix() -> None:
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

    # point=1: each suffix is a duplicate of the other parent's prefix → prefix only.
    assert [gene.candidate.trainer_exercise_id for gene in parent_a] == [
        first_candidate.trainer_exercise_id,
    ]
    assert [gene.candidate.trainer_exercise_id for gene in parent_b] == [
        second_candidate.trainer_exercise_id,
    ]
    assert _unique_exercise_ids(parent_a)
    assert _unique_exercise_ids(parent_b)


def test_structurally_invalid_when_exercise_repeats() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    context = _context(candidate)
    duplicate = PlanIndividual(
        selections=(
            PlanExerciseSelection(1, candidate, 8),
            PlanExerciseSelection(1, candidate, 13),
        )
    )

    assert not is_structurally_valid(context, duplicate)
    assert _evaluate(to_deap(duplicate, 1), context=context) == (-1.0,)


def test_mutation_replace_only_picks_unused_exercise() -> None:
    kept = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    replaced = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", duration=12)
    unused = _candidate("2ac590e1-2a46-4cb7-8944-803e364cc46b", duration=14)
    individual = to_deap(
        PlanIndividual(
            selections=(
                PlanExerciseSelection(1, kept, 10),
                PlanExerciseSelection(1, replaced, 12),
            )
        ),
        1,
    )

    class ReplaceMutationRandom:
        def randint(self, low: int, high: int) -> int:
            return 1

        def randrange(self, stop: int) -> int:
            return 1

        def choice(self, sequence):  # noqa: ANN001
            assert kept not in sequence
            assert replaced in sequence
            assert unused in sequence
            return unused

    _mutate(
        individual,
        candidates=(kept, replaced, unused),
        schema_position=1,
        random=ReplaceMutationRandom(),
    )

    assert individual[1].candidate.trainer_exercise_id == unused.trainer_exercise_id
    assert _unique_exercise_ids(individual)


def test_mutation_can_insert_unused_candidate() -> None:
    kept = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    unused = _candidate("1ac590e1-2a46-4cb7-8944-803e364cc46b", duration=12)
    individual = to_deap(
        PlanIndividual(selections=(PlanExerciseSelection(1, kept, 10),)),
        1,
    )

    class InsertMutationRandom:
        def randint(self, low: int, high: int) -> int:
            return 2

        def randrange(self, stop: int) -> int:
            return stop - 1

        def choice(self, sequence):  # noqa: ANN001
            assert sequence == [unused]
            return unused

    _mutate(
        individual,
        candidates=(kept, unused),
        schema_position=1,
        random=InsertMutationRandom(),
    )

    assert len(individual) == 2
    assert individual[1].candidate.trainer_exercise_id == unused.trainer_exercise_id
    assert individual[1].schema_position == 1
    assert _unique_exercise_ids(individual)


def _unique_exercise_ids(individual) -> bool:  # noqa: ANN001
    ids = [gene.candidate.trainer_exercise_id for gene in individual]
    return len(ids) == len(set(ids))


def test_mutation_can_change_allocated_duration() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b", duration=10)
    individual = to_deap(
        PlanIndividual(selections=(PlanExerciseSelection(1, candidate, 10),)),
        1,
    )

    class DurationMutationRandom:
        def randint(self, low: int, high: int) -> int:
            if (low, high) == (0, 3):
                return 0
            return 3

        def randrange(self, stop: int) -> int:
            return 0

        def choice(self, sequence):  # noqa: ANN001
            return 1

    _mutate(
        individual,
        candidates=(candidate,),
        schema_position=1,
        random=DurationMutationRandom(),
    )

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
        PlanIndividual(selections=(PlanExerciseSelection(1, candidate, 10),)),
    )

    assert best.snapshot() is None


def test_evolve_rejects_an_empty_population() -> None:
    context = _context(_candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b"))

    with pytest.raises(NoValidPlanError):
        evolve(context, InitialPopulation(individuals=()), best=BestSoFar())


def test_from_deap_round_trips_domain_individual() -> None:
    candidate = _candidate("0ac590e1-2a46-4cb7-8944-803e364cc46b")
    original = PlanIndividual(selections=(PlanExerciseSelection(1, candidate, 10),))

    assert from_deap(to_deap(original, 5)) == original
