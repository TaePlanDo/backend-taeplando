"""Response models for the training-type catalog."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CatalogVisibility


class TrainingTypeResponse(BaseModel):
    """One training type visible to the authenticated trainer."""

    id: UUID
    name: str
    visibility: CatalogVisibility
    created_at: datetime
