import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.db import training_segments as training_segments_db
from app.models.catalogs import TrainingSegment
from app.schemas.training_segments import TrainingSegmentResponse
from app.services import training_segment_service


def test_list_segments_requires_authentication(client) -> None:
    """Reject anonymous access to the training-segment catalog."""
    response = client.get("/training-segments")

    assert response.status_code == 401


def test_list_segments_returns_catalog_for_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Return the seeded segment list for an authenticated trainer."""
    segments = [
        TrainingSegmentResponse(id=1, code="WARMUP", name="Rozgrzewka"),
        TrainingSegmentResponse(id=3, code="MAIN", name="Część główna"),
    ]
    with patch(
        "app.api.training_segments.training_segment_service.list_segments",
        new=AsyncMock(return_value=segments),
    ) as list_segments:
        response = client.get("/training-segments")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "code": "WARMUP", "name": "Rozgrzewka"},
        {"id": 3, "code": "MAIN", "name": "Część główna"},
    ]
    list_segments.assert_awaited_once()


def test_list_segments_service_maps_catalog_rows() -> None:
    """Map ORM catalog rows to the public segment response shape."""
    session = AsyncMock()
    with patch(
        "app.services.training_segment_service.training_segments_db.list_all",
        new=AsyncMock(
            return_value=[
                TrainingSegment(id=1, code="WARMUP", name="Rozgrzewka"),
                TrainingSegment(id=3, code="MAIN", name="Część główna"),
            ]
        ),
    ) as list_all:
        result = asyncio.run(training_segment_service.list_segments(session))

    assert result == [
        TrainingSegmentResponse(id=1, code="WARMUP", name="Rozgrzewka"),
        TrainingSegmentResponse(id=3, code="MAIN", name="Część główna"),
    ]
    list_all.assert_awaited_once_with(session)


def test_list_by_ids_filters_to_requested_identifiers() -> None:
    """Load only the catalog rows matching the requested segment ids."""
    session = AsyncMock()
    warmup = TrainingSegment(id=1, code="WARMUP", name="Rozgrzewka")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [warmup]
    session.execute = AsyncMock(return_value=result)

    segments = asyncio.run(training_segments_db.list_by_ids(session, [1, 99]))

    assert segments == [warmup]
    session.execute.assert_awaited_once()
    statement = str(session.execute.await_args.args[0]).lower()
    assert "training_segments" in statement


def test_list_all_orders_by_id() -> None:
    """Return the full catalog ordered by primary key."""
    session = AsyncMock()
    segments = [
        TrainingSegment(id=1, code="WARMUP", name="Rozgrzewka"),
        TrainingSegment(id=3, code="MAIN", name="Część główna"),
    ]
    result = MagicMock()
    result.scalars.return_value.all.return_value = segments
    session.execute = AsyncMock(return_value=result)

    loaded = asyncio.run(training_segments_db.list_all(session))

    assert loaded == segments
    statement = str(session.execute.await_args.args[0]).lower()
    assert "order by" in statement
