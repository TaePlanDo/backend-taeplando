"""Database-free contracts shared by candidate preparation and generation."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.models.enums import EquipmentRequirementMode


@dataclass(frozen=True)
class PlanExerciseCandidate:
    """Complete planning data for one exercise eligible for its segments."""

    trainer_exercise_id: UUID
    exercise_id: UUID
    exercise_version_id: UUID | None
    min_age: int
    max_age: int
    min_participants: int
    max_participants: int
    default_duration_minutes: int
    equipment_requirement_mode: EquipmentRequirementMode
    equipment_ids: tuple[UUID, ...]
    training_type_ids: tuple[UUID, ...]
    segment_ids: tuple[int, ...]
    physical_difficulty: int
    technical_difficulty: int
    upper_body_load: int
    lower_body_load: int
    core_load: int


@dataclass(frozen=True)
class GenerationSchemaItem:
    """One segment allocation available to a plan-generation strategy."""

    position: int
    segment_id: int
    percentage: Decimal


@dataclass(frozen=True)
class GenerationContext:
    """Immutable input for one independently generated training segment."""

    participant_count: int
    available_equipment_ids: tuple[UUID, ...]
    preferred_training_type_id: UUID | None
    training_group_id: UUID
    training_group_name: str
    group_min_age: int
    group_max_age: int
    group_duration_minutes: int
    deadline_at: datetime
    segment: GenerationSchemaItem
    segment_duration_minutes: int
    candidates: tuple[PlanExerciseCandidate, ...]
    random_seed: int


@dataclass(frozen=True)
class PlanExerciseSelection:
    """One exercise gene assigned to one schema position in a plan individual."""

    schema_position: int
    candidate: PlanExerciseCandidate
    allocated_duration_minutes: int


@dataclass(frozen=True)
class PlanIndividual:
    """One candidate set of selected exercise genes."""

    selections: tuple[PlanExerciseSelection, ...]


@dataclass(frozen=True)
class InitialPopulation:
    """The first generation supplied to the genetic algorithm."""

    individuals: tuple[PlanIndividual, ...]
