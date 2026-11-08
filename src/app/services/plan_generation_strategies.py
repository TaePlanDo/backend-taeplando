"""Interchangeable algorithms for selecting a plan from a population."""

from random import Random
from typing import Protocol

from app.services.plan_generation_domain import (
    GenerationContext,
    InitialPopulation,
    PlanIndividual,
)
from app.services.plan_generation_errors import PlanGenerationError


class PlanGenerationStrategy(Protocol):
    """Stateless segment strategy safe to invoke concurrently without I/O."""

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> PlanIndividual:
        """Choose one segment plan from the prepared population without I/O."""


class RandomPlanGenerationStrategy:
    """Temporary deterministic pseudo-random selection used before the GA exists."""

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> PlanIndividual:
        """Choose one prepared plan until the genetic strategy replaces this stub."""
        if not population.individuals:
            raise PlanGenerationError("Initial population is empty")
        random = Random(context.random_seed)
        return random.choice(population.individuals)
