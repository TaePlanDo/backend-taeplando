"""Interchangeable algorithms for selecting a plan from a population."""

from collections.abc import Callable
from random import Random
from typing import Protocol

from app.services.plan_generation_best import BestSoFar
from app.services.plan_generation_domain import (
    GenerationContext,
    InitialPopulation,
    PlanIndividual,
)
from app.services.plan_generation_errors import PlanGenerationError
from app.services.plan_generation_evolution import evolve


class PlanGenerationStrategy(Protocol):
    """Algorithm that generates one segment without I/O."""

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> PlanIndividual:
        """Choose one segment plan from the prepared population without I/O."""


PlanGenerationStrategyFactory = Callable[[BestSoFar], PlanGenerationStrategy]


class GeneticPlanGenerationStrategy:
    """DEAP genetic algorithm for one training-plan segment."""

    def __init__(self, best: BestSoFar) -> None:
        self._best = best

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> PlanIndividual:
        """Evolve one segment plan and publish BestSoFar updates."""
        return evolve(context, population, best=self._best)


class RandomPlanGenerationStrategy:
    """Deterministic pseudo-random selection kept for tests and comparisons."""

    def __init__(self, best: BestSoFar) -> None:
        _ = best

    def generate(
        self, context: GenerationContext, population: InitialPopulation
    ) -> PlanIndividual:
        """Choose one prepared plan from the initial population."""
        if not population.individuals:
            raise PlanGenerationError("Initial population is empty")
        random = Random(context.random_seed)
        return random.choice(population.individuals)
