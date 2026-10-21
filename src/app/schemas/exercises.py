"""Request and response models for exercise catalog endpoints."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ExerciseScope, TrainerExerciseStatus
from app.schemas.common import Description, Name


class ExerciseWrite(BaseModel):
    """Payload used to create one trainer-owned exercise."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description
    duration_minutes: int = Field(gt=0)


class ExerciseResponse(BaseModel):
    """One catalog or trainer-owned exercise available to the trainer."""

    id: UUID
    owner_user_id: UUID
    scope: ExerciseScope
    name: str
    description: str
    duration_minutes: int
    status: TrainerExerciseStatus
