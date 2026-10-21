"""Request and response models for trainer-owned groups."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Name


class GroupWrite(BaseModel):
    """Complete editable payload used to create or replace a group."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    min_age: int = Field(gt=0)
    max_age: int = Field(gt=0)
    duration_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_age_range(self) -> "GroupWrite":
        """Keep the API validation consistent with the database constraint."""
        if self.max_age < self.min_age:
            raise ValueError("max_age must be greater than or equal to min_age")
        return self


class GroupSchemaItemWrite(BaseModel):
    """One ordered segment allocation in a schema replace payload."""

    model_config = ConfigDict(extra="forbid")

    segment_id: int = Field(gt=0)
    percentage: Decimal = Field(gt=0, le=100)


class GroupSchemaWrite(BaseModel):
    """Complete replacement payload for a group's training schema."""

    model_config = ConfigDict(extra="forbid")

    items: list[GroupSchemaItemWrite] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schema_rules(self) -> "GroupSchemaWrite":
        """Enforce unique segments and percentages that sum to 100%."""
        segment_ids = [item.segment_id for item in self.items]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("Each training segment may appear at most once")
        total = sum((item.percentage for item in self.items), Decimal("0"))
        if total != Decimal("100"):
            raise ValueError("Schema percentages must sum to 100")
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
    schema_items: list[GroupSchemaItemResponse] = Field(serialization_alias="schema")
