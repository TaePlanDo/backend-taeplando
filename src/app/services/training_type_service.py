"""Business operations for the training-type catalog."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalogs as catalogs_db
from app.models.catalogs import TrainingType
from app.schemas.common import PaginatedResponse, paginate
from app.schemas.training_types import TrainingTypeResponse


async def list_training_types(
    session: AsyncSession, trainer_id: UUID, *, page: int, page_size: int
) -> PaginatedResponse[TrainingTypeResponse]:
    """Return one page of training types visible to a trainer."""
    db_page = await catalogs_db.list_visible_to_trainer(
        session,
        trainer_id,
        catalog=TrainingType,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return paginate(
        items=[_to_response(training_type) for training_type in db_page.items],
        total=db_page.total,
        page=page,
        page_size=page_size,
    )


def _to_response(training_type: TrainingType) -> TrainingTypeResponse:
    """Map a training-type ORM object to the public API shape."""
    return TrainingTypeResponse(
        id=training_type.id,
        name=training_type.name,
        visibility=training_type.visibility,
        created_at=training_type.created_at,
    )
