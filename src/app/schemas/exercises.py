"""Request and response models for exercise catalog endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.enums import ExerciseScope, TrainerExerciseStatus
from app.schemas.common import Description, Name


class ExerciseUpdate(BaseModel):
    """Editable fields of one trainer-owned exercise."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description
    duration_minutes: int = Field(gt=0)
    image_url: HttpUrl | None = None


class ExerciseWrite(ExerciseUpdate):
    """Payload used to create one trainer-owned exercise."""

    min_age: int = Field(default=1, gt=0)
    max_age: int = Field(default=99, gt=0)
    min_participants: int = Field(default=1, gt=0)
    max_participants: int = Field(default=99, gt=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "ExerciseWrite":
        """Keep exercise ranges consistent with database constraints."""
        if self.max_age < self.min_age:
            raise ValueError("max_age must be greater than or equal to min_age")
        if self.max_participants < self.min_participants:
            raise ValueError(
                "max_participants must be greater than or equal to min_participants"
            )
        return self
class ExerciseResponse(BaseModel):
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
