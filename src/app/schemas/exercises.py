"""Request and response models for exercise catalog endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.enums import (
    EquipmentRequirementMode,
    ExerciseScope,
    TrainerExerciseStatus,
)
from app.schemas.common import Description, Name


class CatalogReference(BaseModel):
    """One named catalog item assigned to an exercise."""

    id: UUID
    name: str


class TrainingSegmentResponse(BaseModel):
    """One fixed training segment assigned to an exercise."""

    id: int
    code: str
    name: str


class ExerciseConfigurationWrite(BaseModel):
    """The complete trainer-managed classification of an exercise."""

    model_config = ConfigDict(extra="forbid")

    equipment_ids: list[UUID] = Field(default_factory=list)
    training_type_ids: list[UUID] = Field(min_length=1)
    segment_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ExerciseConfigurationWrite":
        """Reject duplicate catalog entries before resolving their visibility."""
        fields = ("equipment_ids", "training_type_ids", "segment_ids")
        if any(
            len(getattr(self, field)) != len(set(getattr(self, field)))
            for field in fields
        ):
            raise ValueError("configuration identifiers must not contain duplicates")
        return self


class ExercisePlanningAttributes(BaseModel):
    """Planning metadata shared by exercise writes and responses."""

    equipment_requirement_mode: EquipmentRequirementMode
    physical_difficulty: int = Field(ge=1, le=5)
    technical_difficulty: int = Field(ge=1, le=5)
    upper_body_load: int = Field(ge=1, le=5)
    lower_body_load: int = Field(ge=1, le=5)
    core_load: int = Field(ge=1, le=5)


class ExerciseUpdate(ExerciseConfigurationWrite, ExercisePlanningAttributes):
    """Editable fields of one trainer-owned exercise."""

    name: Name
    description: Description
    duration_minutes: int = Field(gt=0)
    image_url: HttpUrl | None = None
    min_age: int = Field(gt=0)
    max_age: int = Field(gt=0)
    min_participants: int = Field(gt=0)
    max_participants: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ExerciseUpdate":
        """Keep exercise ranges consistent with database constraints."""
        if self.max_age < self.min_age:
            raise ValueError("max_age must be greater than or equal to min_age")
        if self.max_participants < self.min_participants:
            raise ValueError(
                "max_participants must be greater than or equal to min_participants"
            )
        return self


class ExerciseWrite(ExerciseUpdate):
    """Payload used to create one trainer-owned exercise."""

    min_age: int = Field(default=1, gt=0)
    max_age: int = Field(default=99, gt=0)
    min_participants: int = Field(default=1, gt=0)
    max_participants: int = Field(default=99, gt=0)
    equipment_requirement_mode: EquipmentRequirementMode = EquipmentRequirementMode.ALL
    physical_difficulty: int = Field(default=3, ge=1, le=5)
    technical_difficulty: int = Field(default=3, ge=1, le=5)
    upper_body_load: int = Field(default=3, ge=1, le=5)
    lower_body_load: int = Field(default=3, ge=1, le=5)
    core_load: int = Field(default=3, ge=1, le=5)


class ExerciseResponse(ExercisePlanningAttributes):
    """One catalog or trainer-owned exercise available to the trainer."""

    id: UUID
    owner_user_id: UUID
    scope: ExerciseScope
    name: str
    description: str
    image_url: str | None
    min_age: int
    max_age: int
    min_participants: int
    max_participants: int
    duration_minutes: int
    status: TrainerExerciseStatus
    equipment: list[CatalogReference]
    training_types: list[CatalogReference]
    segments: list[TrainingSegmentResponse]
