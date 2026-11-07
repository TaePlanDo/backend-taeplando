"""Build the first generation from already filtered exercise candidates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from random import Random
from typing import TYPE_CHECKING

from app.services.plan_generation_candidates_service import PlanExerciseCandidate
from app.services.plan_generation_errors import NoCandidateForSchemaPositionError

if TYPE_CHECKING:
    from app.services.plan_generation_strategies import GenerationContext


INITIAL_POPULATION_SIZE = 20


@dataclass(frozen=True)
class PlanExerciseSelection:
    """One exercise gene assigned to one schema position in a plan individual."""

    schema_position: int
    candidate: PlanExerciseCandidate
    allocated_duration_minutes: int


@dataclass(frozen=True)
class PlanIndividual:
    """One complete candidate plan in the genetic population."""

    selections: tuple[PlanExerciseSelection, ...]


@dataclass(frozen=True)
class InitialPopulation:
    """The first generation supplied to the genetic algorithm."""

    individuals: tuple[PlanIndividual, ...]


def build_initial_population(
    context: GenerationContext,
    *,
    population_size: int = INITIAL_POPULATION_SIZE,
) -> InitialPopulation:
    """Create deterministic, structurally valid plans from eligible candidates."""
    if population_size < 1:
        raise ValueError("Population size must be positive")

    candidates_by_position = _candidates_by_position(context)
    random = Random(context.random_seed)
    return InitialPopulation(
        individuals=tuple(
            _individual(context, candidates_by_position, random)
            for _ in range(population_size)
        )
    )


def _individual(
    context: GenerationContext,
    candidates_by_position: dict[int, list[PlanExerciseCandidate]],
    random: Random,
) -> PlanIndividual:
    """Choose one eligible exercise per schema position for a new individual."""
    return PlanIndividual(
        selections=tuple(
            _selection(schema_item.position, candidates_by_position, random)
            for schema_item in context.schema
        )
    )


def _selection(
    schema_position: int,
    candidates_by_position: dict[int, list[PlanExerciseCandidate]],
    random: Random,
) -> PlanExerciseSelection:
    """Choose one candidate and initialize its own duration gene."""
    candidate = random.choice(candidates_by_position[schema_position])
    return PlanExerciseSelection(
        schema_position=schema_position,
        candidate=candidate,
        allocated_duration_minutes=candidate.default_duration_minutes,
    )


def _candidates_by_position(
    context: GenerationContext,
) -> dict[int, list[PlanExerciseCandidate]]:
    """Index only structurally valid candidates by the schema slots they can fill."""
    candidates_by_position: dict[int, list[PlanExerciseCandidate]] = defaultdict(list)
    for candidate in context.candidates:
        if candidate.default_duration_minutes < 1:
            continue
        for schema_position in candidate.schema_positions:
            candidates_by_position[schema_position].append(candidate)

    for schema_item in context.schema:
        if not candidates_by_position[schema_item.position]:
            raise NoCandidateForSchemaPositionError(schema_item.position)
    return candidates_by_position
