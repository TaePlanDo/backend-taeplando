"""Request and response models for trainer-owned groups."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GroupWrite(BaseModel):
    """Complete editable payload used to create or replace a group."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    min_age: int = Field(gt=0)
    max_age: int = Field(gt=0)
    duration_minutes: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Reject names consisting only of whitespace."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_age_range(self) -> "GroupWrite":
        """Keep the API validation consistent with the database constraint."""
        if self.max_age < self.min_age:
            raise ValueError("max_age must be greater than or equal to min_age")
        return self


class GroupSchemaItemResponse(BaseModel):
    """One immutable segment allocation in a group's current schema."""

    segment_id: int
    segment_code: str
    segment_name: str
    percentage: Decimal
    position: int


class GroupResponse(BaseModel):
    """A trainer-owned group and the schema used for new training plans."""

    id: UUID
    trainer_id: UUID
    name: str
    min_age: int
    max_age: int
    duration_minutes: int
    created_at: datetime
    updated_at: datetime
    plan_ids: list[UUID]
    schema_items: list[GroupSchemaItemResponse] = Field(
        serialization_alias="schema"
    )
