"""Input contract for the future training-plan generation flow."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import PlanGenerationJobStatus


class PlanGenerationParameters(BaseModel):
    """Parameters accepted before a training plan is generated."""

    model_config = ConfigDict(extra="forbid")

    training_group_id: UUID
    participant_count: int = Field(gt=0)
    available_equipment_ids: list[UUID]
    training_type_id: UUID | None = None

    @model_validator(mode="after")
    def validate_unique_equipment_ids(self) -> "PlanGenerationParameters":
        """Reject duplicate equipment selections before database validation."""
        if len(self.available_equipment_ids) != len(set(self.available_equipment_ids)):
            raise ValueError("available_equipment_ids must not contain duplicates")
        return self


class PlanGenerationAccepted(BaseModel):
    """The accepted asynchronous generation request returned to the frontend."""

    id: UUID
    status: PlanGenerationJobStatus


class PlanGenerationStatusResponse(PlanGenerationAccepted):
    """Current state and terminal outcome of one generation request."""

    plan_id: UUID | None
    error_code: str | None
    error_message: str | None
