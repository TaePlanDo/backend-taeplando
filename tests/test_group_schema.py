import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.models.catalogs import TrainingSegment
from app.models.training import (
    TrainingGroup,
    TrainingGroupSchemaItem,
    TrainingPlan,
)
from app.schemas.training import (
    GroupResponse,
    GroupSchemaItemResponse,
    GroupSchemaWrite,
)
from app.services import training_group_service
from app.services.training_group_service import GroupNotFoundError, InvalidSchemaError
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
PLAN_ID = UUID("88fa8385-5b07-4346-9ddb-02806890ae4b")
CREATED_AT = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 10, 11, 13, 0, tzinfo=UTC)


def _group_response() -> GroupResponse:
    """Build one complete group response used by schema route tests."""
    return GroupResponse(
        id=GROUP_ID,
        trainer_id=TRAINER_ID,
        name="Młodzież",
        min_age=7,
        max_age=14,
        duration_minutes=60,
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
        plan_ids=[PLAN_ID],
        schema_items=[
            GroupSchemaItemResponse(
                segment_id=3,
                segment_code="MAIN",
                segment_name="Część główna",
                percentage=100,
                position=1,
            )
        ],
    )


def _training_group() -> TrainingGroup:
    """Build one ORM group with the relations schema replace mutates."""
    group = TrainingGroup(
        id=GROUP_ID,
        trainer_id=TRAINER_ID,
        name="Młodzież",
        min_age=7,
        max_age=14,
        duration_minutes=60,
        created_at=CREATED_AT,
        updated_at=UPDATED_AT,
    )
    group.training_plans = [TrainingPlan(id=PLAN_ID)]
    group.schema_items = [
        TrainingGroupSchemaItem(
            segment=TrainingSegment(id=3, code="MAIN", name="Część główna"),
            percentage=Decimal("100"),
            position=1,
        )
    ]
    return group


def test_put_group_schema_rejects_empty_items(client, authenticated_trainer) -> None:
    """Require at least one schema item in the replace payload."""
    response = client.put(f"/training-groups/{GROUP_ID}/schema", json={"items": []})

    assert response.status_code == 422


def test_put_group_schema_rejects_duplicate_segment_ids(
    client, authenticated_trainer
) -> None:
    """Reject a schema that uses the same segment label more than once."""
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(),
    ) as replace_schema:
        response = client.put(
            f"/training-groups/{GROUP_ID}/schema",
            json={
                "items": [
                    {"segment_id": 1, "percentage": 50},
                    {"segment_id": 1, "percentage": 50},
                ]
            },
        )

    assert response.status_code == 422
    replace_schema.assert_not_awaited()


def test_put_group_schema_rejects_percentages_that_do_not_sum_to_100(
    client, authenticated_trainer
) -> None:
    """Reject a schema whose percentages do not total exactly 100."""
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(),
    ) as replace_schema:
        response = client.put(
            f"/training-groups/{GROUP_ID}/schema",
            json={
                "items": [
                    {"segment_id": 1, "percentage": 40},
                    {"segment_id": 3, "percentage": 40},
                ]
            },
        )

    assert response.status_code == 422
    replace_schema.assert_not_awaited()


@pytest.mark.parametrize(
    "percentage",
    [0, 100.01, -5],
)
def test_put_group_schema_rejects_out_of_range_percentages(
    client, authenticated_trainer, percentage: float
) -> None:
    """Reject per-item percentages outside the open-closed (0, 100] range."""
    response = client.put(
        f"/training-groups/{GROUP_ID}/schema",
        json={"items": [{"segment_id": 3, "percentage": percentage}]},
    )

    assert response.status_code == 422


def test_put_group_schema_rejects_extra_fields(client, authenticated_trainer) -> None:
    """Forbid client-supplied position and other unknown schema fields."""
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(),
    ) as replace_schema:
        response = client.put(
            f"/training-groups/{GROUP_ID}/schema",
            json={
                "items": [
                    {"segment_id": 3, "percentage": 100, "position": 1},
                ]
            },
        )

    assert response.status_code == 422
    replace_schema.assert_not_awaited()


def test_put_group_schema_replaces_schema_for_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Forward a valid schema payload and return the updated group response."""
    group = _group_response()
    group.schema_items = [
        GroupSchemaItemResponse(
            segment_id=1,
            segment_code="WARMUP",
            segment_name="Rozgrzewka",
            percentage=Decimal("20"),
            position=1,
        ),
        GroupSchemaItemResponse(
            segment_id=3,
            segment_code="MAIN",
            segment_name="Część główna",
            percentage=Decimal("70"),
            position=2,
        ),
        GroupSchemaItemResponse(
            segment_id=4,
            segment_code="COOLDOWN",
            segment_name="Wyciszenie",
            percentage=Decimal("10"),
            position=3,
        ),
    ]
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(return_value=group),
    ) as replace_schema:
        response = client.put(
            f"/training-groups/{GROUP_ID}/schema",
            json={
                "items": [
                    {"segment_id": 1, "percentage": 20},
                    {"segment_id": 3, "percentage": 70},
                    {"segment_id": 4, "percentage": 10},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json()["schema"] == [
        {
            "segment_id": 1,
            "segment_code": "WARMUP",
            "segment_name": "Rozgrzewka",
            "percentage": "20",
            "position": 1,
        },
        {
            "segment_id": 3,
            "segment_code": "MAIN",
            "segment_name": "Część główna",
            "percentage": "70",
            "position": 2,
        },
        {
            "segment_id": 4,
            "segment_code": "COOLDOWN",
            "segment_name": "Wyciszenie",
            "percentage": "10",
            "position": 3,
        },
    ]
    assert replace_schema.await_args.args[1] == TRAINER_ID
    assert replace_schema.await_args.args[2] == GROUP_ID
    payload = replace_schema.await_args.args[3]
    assert isinstance(payload, GroupSchemaWrite)
    assert [item.segment_id for item in payload.items] == [1, 3, 4]


def test_put_group_schema_returns_not_found_for_foreign_or_missing_group(
    client, authenticated_trainer
) -> None:
    """Hide whether a missing group belongs to another trainer."""
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(side_effect=GroupNotFoundError),
    ):
        response = client.put(
            f"/training-groups/{uuid4()}/schema",
            json={"items": [{"segment_id": 3, "percentage": 100}]},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Group not found"}


def test_put_group_schema_returns_422_for_unknown_segment(
    client, authenticated_trainer
) -> None:
    """Reject schema items whose segment ids are absent from the catalog."""
    with patch(
        "app.api.training_groups.training_group_service.replace_group_schema",
        new=AsyncMock(side_effect=InvalidSchemaError),
    ):
        response = client.put(
            f"/training-groups/{GROUP_ID}/schema",
            json={"items": [{"segment_id": 999, "percentage": 100}]},
        )

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown training segment id(s)"}


def test_replace_group_schema_assigns_positions_and_commits_once() -> None:
    """Replace schema items in one commit and derive positions from array order."""
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    group = _training_group()
    warmup = TrainingSegment(id=1, code="WARMUP", name="Rozgrzewka")
    main = TrainingSegment(id=3, code="MAIN", name="Część główna")
    cooldown = TrainingSegment(id=4, code="COOLDOWN", name="Wyciszenie")
    payload = GroupSchemaWrite(
        items=[
            {"segment_id": 1, "percentage": Decimal("20")},
            {"segment_id": 3, "percentage": Decimal("70")},
            {"segment_id": 4, "percentage": Decimal("10")},
        ]
    )
    expected = _group_response()
    with (
        patch(
            "app.services.training_group_service.training_groups_db.get_for_trainer",
            new=AsyncMock(return_value=group),
        ),
        patch(
            "app.services.training_group_service.training_segments_db.list_by_ids",
            new=AsyncMock(return_value=[warmup, main, cooldown]),
        ) as list_segments,
        patch.object(
            training_group_service,
            "_to_response",
            return_value=expected,
        ),
    ):
        result = asyncio.run(
            training_group_service.replace_group_schema(
                session, TRAINER_ID, GROUP_ID, payload
            )
        )

    assert result == expected
    list_segments.assert_awaited_once()
    assert [item.segment.id for item in group.schema_items] == [1, 3, 4]
    assert [item.percentage for item in group.schema_items] == [
        Decimal("20"),
        Decimal("70"),
        Decimal("10"),
    ]
    assert [item.position for item in group.schema_items] == [1, 2, 3]
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_replace_group_schema_rejects_unknown_segment_ids() -> None:
    """Fail before mutating when any segment id is missing from the catalog."""
    session = MagicMock()
    session.commit = AsyncMock()
    group = _training_group()
    original_items = list(group.schema_items)
    payload = GroupSchemaWrite(
        items=[{"segment_id": 999, "percentage": Decimal("100")}]
    )
    with (
        patch(
            "app.services.training_group_service.training_groups_db.get_for_trainer",
            new=AsyncMock(return_value=group),
        ),
        patch(
            "app.services.training_group_service.training_segments_db.list_by_ids",
            new=AsyncMock(return_value=[]),
        ),
        pytest.raises(InvalidSchemaError),
    ):
        asyncio.run(
            training_group_service.replace_group_schema(
                session, TRAINER_ID, GROUP_ID, payload
            )
        )

    assert group.schema_items == original_items
    session.commit.assert_not_awaited()


def test_replace_group_schema_raises_when_group_is_missing() -> None:
    """Propagate a uniform not-found outcome for foreign or missing groups."""
    session = MagicMock()
    payload = GroupSchemaWrite(items=[{"segment_id": 3, "percentage": Decimal("100")}])
    with (
        patch(
            "app.services.training_group_service.training_groups_db.get_for_trainer",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(GroupNotFoundError),
    ):
        asyncio.run(
            training_group_service.replace_group_schema(
                session, TRAINER_ID, GROUP_ID, payload
            )
        )
