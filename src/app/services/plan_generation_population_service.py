"""Build the first generation from already filtered exercise candidates."""

from __future__ import annotations

from random import Random

from app.services.plan_generation_domain import (
    GenerationContext,
    InitialPopulation,
    PlanExerciseSelection,
    PlanIndividual,
)

INITIAL_POPULATION_SIZE = 20


def build_initial_population(
    context: GenerationContext,
    *,
    population_size: int = INITIAL_POPULATION_SIZE,
) -> InitialPopulation:
    """Create deterministic, structurally valid plans from eligible candidates."""
    if population_size < 1:
        raise ValueError("Population size must be positive")

    random = Random(context.random_seed)
    return InitialPopulation(
        individuals=tuple(_individual(context, random) for _ in range(population_size))
    )


def _individual(
    context: GenerationContext,
    random: Random,
) -> PlanIndividual:
    """Choose one eligible exercise per schema position for a new individual."""
    return PlanIndividual(
        selections=tuple(
            _selection(schema_item.position, context, random)
            for schema_item in context.schema
        )
    )


def _selection(
    schema_position: int,
    context: GenerationContext,
    random: Random,
) -> PlanExerciseSelection:
    """Choose one candidate and initialize its own duration gene."""
    candidate = random.choice(
        context.candidate_pool.by_schema_position[schema_position]
    )
    return PlanExerciseSelection(
        schema_position=schema_position,
        candidate=candidate,
        allocated_duration_minutes=candidate.default_duration_minutes,
    )
