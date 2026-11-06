"""Request filters and response models for trainer plan history."""

from datetime import datetime
from typing import NamedTuple
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.exercises import CatalogReference, TrainingSegmentResponse


class TrainingPlanListFilters(NamedTuple):
    """Normalized filters applied to a trainer's saved-plan list."""

    name: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    min_participants: int | None = None
    max_participants: int | None = None
    min_duration: int | None = None
    max_duration: int | None = None
    equipment_ids: list[UUID] | None = None
    training_type_ids: list[UUID] | None = None
    training_group_ids: list[UUID] | None = None


EMPTY_TRAINING_PLAN_LIST_FILTERS = TrainingPlanListFilters()


class PlanSchemaSnapshotItem(BaseModel):
    """One segment allocation frozen into a historical plan."""

    position: int
    segment_id: int
    code: str
    name: str
    percentage: float


class PlanExerciseResponse(BaseModel):
    """One immutable exercise occurrence inside a saved plan."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    trainer_exercise_id: UUID
    exercise_id: UUID
    exercise_version_id: UUID | None
    position: int
    schema_position: int
    name_snapshot: str
    description_snapshot: str
    image_url_snapshot: str | None
    min_age_snapshot: int
    max_age_snapshot: int
    min_participants_snapshot: int
    max_participants_snapshot: int
    duration_minutes_snapshot: int
    physical_difficulty_snapshot: int = Field(ge=1, le=5)
    technical_difficulty_snapshot: int = Field(ge=1, le=5)
    upper_body_load_snapshot: int = Field(ge=1, le=5)
    lower_body_load_snapshot: int = Field(ge=1, le=5)
    core_load_snapshot: int = Field(ge=1, le=5)
    equipment_snapshot: list[CatalogReference]
    training_types_snapshot: list[CatalogReference]
    segments_snapshot: list[TrainingSegmentResponse]


class PlanListItem(BaseModel):
    """One saved plan as shown on the history list and recent-plans modal."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    training_group_id: UUID
    name: str
    participant_count: int
    group_name_snapshot: str
    group_min_age_snapshot: int
    group_max_age_snapshot: int
    training_duration_snapshot: int
    available_equipment_snapshot: list[CatalogReference]
    training_types_snapshot: list[CatalogReference]
    schema_snapshot: list[PlanSchemaSnapshotItem]
    generated_at: datetime


class PlanDetail(PlanListItem):
    """A saved plan together with its ordered exercise snapshots."""

    exercises: list[PlanExerciseResponse] = Field(default_factory=list)
