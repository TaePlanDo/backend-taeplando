"""Request and response models for training equipment."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import CatalogVisibility
from app.schemas.common import Name


class EquipmentWrite(BaseModel):
    """Payload used to create one equipment type."""

    model_config = ConfigDict(extra="forbid")

    name: Name


class EquipmentResponse(BaseModel):
    """One equipment type visible to the authenticated trainer."""

    id: UUID
    name: str
    visibility: CatalogVisibility
    created_at: datetime
