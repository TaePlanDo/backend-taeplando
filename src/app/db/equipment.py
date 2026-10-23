"""Database helpers for trainer-owned equipment."""

from uuid import UUID

from app.models.catalogs import Equipment
from app.models.enums import CatalogVisibility


def create_for_trainer(trainer_id: UUID, name: str) -> Equipment:
    """Build a local equipment type owned by one trainer."""
    return Equipment(
        owner_user_id=trainer_id,
        name=name,
        visibility=CatalogVisibility.LOCAL,
    )
