"""Request and response models for training equipment."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import CatalogVisibility


class EquipmentWrite(BaseModel):
    """Payload used to create one equipment type."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        """Trim a name and reject whitespace-only values."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Name cannot be blank")
        return normalized


class EquipmentResponse(BaseModel):
    """One equipment type visible to the authenticated trainer."""

    id: UUID
    name: str
    visibility: CatalogVisibility
    created_at: datetime
