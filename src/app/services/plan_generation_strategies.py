"""Interchangeable algorithms for selecting exercises for a generated plan."""

from dataclasses import dataclass
from datetime import datetime
from random import Random
from typing import Protocol

from app.services.plan_generation_candidates_service import PlanExerciseCandidate
from app.services.plan_generation_errors import (
    NoCandidateForSchemaPositionError,
    PlanGenerationError,
)
from app.services.plan_generation_population_service import (
    InitialPopulation,
    PlanExerciseSelection,
)

__all__ = [
    "GeneratedPlan",
    "GenerationContext",
    "GenerationSchemaItem",
    "NoCandidateForSchemaPositionError",
    "PlanGenerationError",
    "PlanGenerationStrategy",
    "RandomPlanGenerationStrategy",
]


@dataclass(frozen=True)
class GenerationSchemaItem:
    """One segment allocation available to a plan-generation strategy."""

    position: int
    segment_id: int
    percentage: float


@dataclass(frozen=True)
class GenerationContext:
    """Immutable, database-free input shared by every generation strategy."""

    group_duration_minutes: int
    deadline_at: datetime
    schema: tuple[GenerationSchemaItem, ...]
    candidates: tuple[PlanExerciseCandidate, ...]
    random_seed: int


@dataclass(frozen=True)
class GeneratedPlan:
    """Algorithm output that the runner can persist without rerunning selection."""

    exercises: tuple[PlanExerciseSelection, ...]


class PlanGenerationStrategy(Protocol):
    """Select exercises without performing I/O or changing persistent state."""

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> GeneratedPlan:
        """Choose one plan from the prepared population without performing I/O."""


class RandomPlanGenerationStrategy:
    """Temporary deterministic pseudo-random selection used before the GA exists."""

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> GeneratedPlan:
        """Choose one prepared plan until the genetic strategy replaces this stub."""
        if not population.individuals:
            raise PlanGenerationError("Initial population is empty")
        random = Random(context.random_seed)
        individual = random.choice(population.individuals)
        return GeneratedPlan(exercises=individual.selections)
