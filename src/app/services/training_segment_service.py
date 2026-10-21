"""Business operations for the fixed training-segment catalog."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import training_segments as training_segments_db
from app.models.catalogs import TrainingSegment
from app.schemas.training_segments import TrainingSegmentResponse


async def list_segments(session: AsyncSession) -> list[TrainingSegmentResponse]:
    """Return the full seeded training-segment catalog."""
    segments = await training_segments_db.list_all(session)
    return [_to_response(segment) for segment in segments]


def _to_response(segment: TrainingSegment) -> TrainingSegmentResponse:
    """Map a catalog segment to the API response shape."""
    return TrainingSegmentResponse(
        id=segment.id,
        code=segment.code,
        name=segment.name,
    )
