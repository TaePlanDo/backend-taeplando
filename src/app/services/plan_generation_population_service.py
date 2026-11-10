"""Build the first generation from already filtered exercise candidates."""

from __future__ import annotations

from decimal import Decimal
from random import Random

from app.services.plan_generation_constants import INITIAL_POPULATION_SIZE
from app.services.plan_generation_domain import (
    GenerationContext,
    GenerationSchemaItem,
    InitialPopulation,
    PlanExerciseCandidate,
    PlanExerciseSelection,
    PlanIndividual,
)
from app.services.plan_generation_errors import (
    InvalidSchemaPercentageTotalError,
    NoDurationForSchemaPositionError,
)


def build_initial_population(
    context: GenerationContext,
    *,
    population_size: int = INITIAL_POPULATION_SIZE,
) -> InitialPopulation:
    """Create deterministic, structurally valid plans from eligible candidates."""
    if population_size < 1:
        raise ValueError("Population size must be positive")
    random = Random(context.random_seed)
    if context.segment_duration_minutes < 1:
        raise NoDurationForSchemaPositionError(context.segment.position)
    return InitialPopulation(
        individuals=tuple(
            _individual(context, context.candidates, random)
            for _ in range(population_size)
        )
    )


def _individual(
    context: GenerationContext,
    candidates: tuple[PlanExerciseCandidate, ...],
    random: Random,
) -> PlanIndividual:
    """Greedily pack default-duration exercises under the segment minute budget."""
    return PlanIndividual(
        selections=_selections_for_position(
            schema_position=context.segment.position,
            target_duration=context.segment_duration_minutes,
            candidates=candidates,
            random=random,
        )
    )


def _selections_for_position(
    schema_position: int,
    target_duration: int,
    candidates: tuple[PlanExerciseCandidate, ...],
    random: Random,
) -> tuple[PlanExerciseSelection, ...]:
    """Pack longest fitting defaults; never stretch allocations to fill leftovers."""
    remaining_duration = target_duration
    available_candidates = list(candidates)
    selections: list[PlanExerciseSelection] = []

    while fitting_candidates := [
        candidate
        for candidate in available_candidates
        if candidate.default_duration_minutes <= remaining_duration
    ]:
        longest_duration = max(
            candidate.default_duration_minutes for candidate in fitting_candidates
        )
        candidate = random.choice(
            [
                candidate
                for candidate in fitting_candidates
                if candidate.default_duration_minutes == longest_duration
            ]
        )
        available_candidates.remove(candidate)
        selections.append(
            PlanExerciseSelection(
                schema_position=schema_position,
                candidate=candidate,
                allocated_duration_minutes=candidate.default_duration_minutes,
            )
        )
        remaining_duration -= candidate.default_duration_minutes

    if not selections:
        candidate = _closest_candidate(candidates, target_duration, random)
        return (
            PlanExerciseSelection(
                schema_position=schema_position,
                candidate=candidate,
                allocated_duration_minutes=candidate.default_duration_minutes,
            ),
        )

    return tuple(selections)


def _closest_candidate(
    candidates: tuple[PlanExerciseCandidate, ...],
    target_duration: int,
    random: Random,
) -> PlanExerciseCandidate:
    """Choose a deterministic-random tie among candidates closest to the target."""
    closest_difference = min(
        abs(candidate.default_duration_minutes - target_duration)
        for candidate in candidates
    )
    return random.choice(
        [
            candidate
            for candidate in candidates
            if abs(candidate.default_duration_minutes - target_duration)
            == closest_difference
        ]
    )


def allocate_segment_durations(
    group_duration_minutes: int,
    schema: tuple[GenerationSchemaItem, ...],
) -> dict[int, int]:
    """Split one plan duration by schema percentages without losing minutes."""
    if sum((item.percentage for item in schema), Decimal("0")) != Decimal("100"):
        raise InvalidSchemaPercentageTotalError()
    exact_durations = {
        item.position: (
            Decimal(group_duration_minutes) * item.percentage / Decimal("100")
        )
        for item in schema
    }
    durations = {
        position: int(exact_duration)
        for position, exact_duration in exact_durations.items()
    }
    remaining_minutes = group_duration_minutes - sum(durations.values())
    positions_by_remainder = sorted(
        exact_durations,
        key=lambda position: (
            exact_durations[position] - durations[position],
            -position,
        ),
        reverse=True,
    )
    for position in positions_by_remainder[:remaining_minutes]:
        durations[position] += 1

    for position, duration in durations.items():
        if duration < 1:
            raise NoDurationForSchemaPositionError(position)
    return durations
