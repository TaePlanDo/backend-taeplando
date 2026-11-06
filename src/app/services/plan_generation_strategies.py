"""Interchangeable algorithms for selecting exercises for a generated plan."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from random import Random
from typing import ClassVar, Protocol

from app.services.plan_generation_candidates_service import PlanExerciseCandidate


class PlanGenerationError(Exception):
    """Base error raised by an algorithm before a plan can be persisted."""

    error_code: ClassVar[str] = "GENERATION_ERROR"


class NoCandidateForSchemaPositionError(PlanGenerationError):
    """Raised when no filtered exercise can fill one schema position."""

    error_code = "NO_CANDIDATE"

    def __init__(self, schema_position: int) -> None:
        self.schema_position = schema_position
        super().__init__(f"No exercise can fill schema position {schema_position}")


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
class GeneratedPlanExercise:
    """One candidate selected by a strategy for one schema position."""

    candidate: PlanExerciseCandidate
    schema_position: int


@dataclass(frozen=True)
class GeneratedPlan:
    """Algorithm output that the runner can persist without rerunning selection."""

    exercises: tuple[GeneratedPlanExercise, ...]


class PlanGenerationStrategy(Protocol):
    """Select exercises without performing I/O or changing persistent state."""

    def generate(self, context: GenerationContext) -> GeneratedPlan:
        """Return one selected candidate for each requested schema position."""


class RandomPlanGenerationStrategy:
    """Temporary deterministic pseudo-random selection used before the GA exists."""

    def generate(self, context: GenerationContext) -> GeneratedPlan:
        """Select candidates independently without considering total duration."""
        candidates_by_position: dict[int, list[PlanExerciseCandidate]] = defaultdict(
            list
        )
        for candidate in context.candidates:
            for position in candidate.schema_positions:
                candidates_by_position[position].append(candidate)

        random = Random(context.random_seed)
        selections: list[GeneratedPlanExercise] = []
        for schema_item in context.schema:
            position = schema_item.position
            candidates = candidates_by_position[position]
            if not candidates:
                raise NoCandidateForSchemaPositionError(position)
            selections.append(
                GeneratedPlanExercise(
                    candidate=random.choice(candidates), schema_position=position
                )
            )
        return GeneratedPlan(exercises=tuple(selections))


def get_plan_generation_strategy() -> PlanGenerationStrategy:
    """Resolve the algorithm behind the stable strategy contract."""
    return RandomPlanGenerationStrategy()
