import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.dependencies.auth import get_current_user
from app.main import app
from app.models.catalogs import TrainingSegment
from app.models.training import TrainingGroup, TrainingPlan
from app.schemas.auth import UserResponse
from app.schemas.training import (
    TrainingGroupResponse,
    TrainingGroupSchemaItemResponse,
    TrainingGroupWrite,
)
from app.services import training_group_service
from app.services.training_group_service import TrainingGroupNotFoundError

TRAINER_ID = UUID("d9aa16f7-b30a-4887-890b-247f86a2eef5")
GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
PLAN_ID = UUID("88fa8385-5b07-4346-9ddb-02806890ae4b")
CREATED_AT = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 10, 11, 13, 0, tzinfo=UTC)


@pytest.fixture
def authenticated_trainer() -> None:
    """Authenticate route tests without involving JWT parsing."""
    app.dependency_overrides[get_current_user] = lambda: UserResponse(
        id=str(TRAINER_ID),
        email="trainer@example.com",
        full_name="Trainer",
        auth_method="LOCAL",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _group_response() -> TrainingGroupResponse:
    """Build one complete group response used by route tests."""
    return TrainingGroupResponse(
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
            TrainingGroupSchemaItemResponse(
                segment_id=3,
                segment_code="MAIN",
                segment_name="Część główna",
                percentage=100,
                position=1,
            )
        ],
    )


def test_list_groups_returns_only_current_trainers_groups(
    client, authenticated_trainer
) -> None:
    """List only the OAuth trainer's groups and forward the optional filters."""
    group = _group_response()
    with patch(
        "app.api.training_groups.training_group_service.list_training_groups",
        new=AsyncMock(return_value=[group]),
    ) as list_groups:
        response = client.get(
            "/training-groups?duration_minutes=60&min_age=7&max_age=14"
        )

    assert response.status_code == 200
    assert response.json() == [group.model_dump(mode="json", by_alias=True)]
    list_groups.assert_awaited_once()
    assert list_groups.await_args.args[1] == TRAINER_ID
    assert list_groups.await_args.kwargs == {
        "duration_minutes": 60,
        "min_age": 7,
        "max_age": 14,
    }


def test_create_group_uses_authenticated_trainer_and_returns_service_response(
    client, authenticated_trainer
) -> None:
    """Create a group for the OAuth trainer and serialize the service response."""
    group = _group_response()
    with patch(
        "app.api.training_groups.training_group_service.create_training_group",
        new=AsyncMock(return_value=group),
    ) as create_group:
        response = client.post(
            "/training-groups",
            json={
                "name": "Młodzież",
                "min_age": 7,
                "max_age": 14,
                "duration_minutes": 60,
            },
        )

    assert response.status_code == 201
    assert response.json()["schema"] == [
        {
            "segment_id": 3,
            "segment_code": "MAIN",
            "segment_name": "Część główna",
            "percentage": "100",
            "position": 1,
        }
    ]
    assert create_group.await_args.args[1] == TRAINER_ID


def test_create_training_group_builds_the_default_main_schema() -> None:
    """Create each group with one 100% MAIN schema item."""
    session = MagicMock()
    session.commit = AsyncMock()
    main_segment = TrainingSegment(id=3, code="MAIN", name="Część główna")
    expected_response = _group_response()
    payload = TrainingGroupWrite(
        name="Młodzież", min_age=7, max_age=14, duration_minutes=60
    )
    with (
        patch(
            "app.db.training_groups.get_training_segment_by_code",
            new=AsyncMock(return_value=main_segment),
        ) as get_segment,
        patch.object(
            training_group_service,
            "_to_response",
            return_value=expected_response,
        ),
    ):
        result = asyncio.run(
            training_group_service.create_training_group(session, TRAINER_ID, payload)
        )

    group = session.add.call_args.args[0]
    schema_item = group.schema_items[0]
    assert result == expected_response
    get_segment.assert_awaited_once_with(session, "MAIN")
    assert group.trainer_id == TRAINER_ID
    assert schema_item.segment is main_segment
    assert schema_item.percentage == 100
    assert schema_item.position == 1
    session.commit.assert_awaited_once()


def test_create_group_rejects_invalid_age_range(client, authenticated_trainer) -> None:
    """Reject a creation payload where the maximum age is below the minimum."""
    response = client.post(
        "/training-groups",
        json={
            "name": "Młodzież",
            "min_age": 14,
            "max_age": 7,
            "duration_minutes": 60,
        },
    )

    assert response.status_code == 422


def test_create_group_rejects_identifiers_in_body(
    client, authenticated_trainer
) -> None:
    """Reject IDs because ownership is derived from the OAuth user."""
    with patch(
        "app.api.training_groups.training_group_service.create_training_group",
        new=AsyncMock(),
    ) as create_group:
        response = client.post(
            "/training-groups",
            json={
                "name": "Młodzież",
                "min_age": 7,
                "max_age": 14,
                "duration_minutes": 60,
                "id": str(uuid4()),
                "trainer_id": str(uuid4()),
            },
        )

    assert response.status_code == 422
    create_group.assert_not_awaited()


def test_get_group_returns_not_found_for_a_foreign_or_missing_group(
    client, authenticated_trainer
) -> None:
    """Do not expose whether a missing group belongs to another trainer."""
    with patch(
        "app.api.training_groups.training_group_service.get_training_group",
        new=AsyncMock(side_effect=TrainingGroupNotFoundError),
    ):
        response = client.get(f"/training-groups/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Group not found"}


def test_get_group_returns_only_plan_identifiers(client, authenticated_trainer) -> None:
    """Expose related plan UUIDs without embedding complete plan records."""
    group = _group_response()
    with patch(
        "app.api.training_groups.training_group_service.get_training_group",
        new=AsyncMock(return_value=group),
    ):
        response = client.get(f"/training-groups/{GROUP_ID}")

    assert response.status_code == 200
    assert response.json()["plan_ids"] == [str(PLAN_ID)]


def test_put_group_requires_all_editable_fields(client, authenticated_trainer) -> None:
    """Require a complete replacement payload for the PUT endpoint."""
    response = client.put(f"/training-groups/{GROUP_ID}", json={"min_age": 18})

    assert response.status_code == 422


def test_put_group_rejects_identifiers_in_body(client, authenticated_trainer) -> None:
    """Reject IDs because the URL and OAuth context supply them."""
    with patch(
        "app.api.training_groups.training_group_service.put_training_group",
        new=AsyncMock(),
    ) as put_group:
        response = client.put(
            f"/training-groups/{GROUP_ID}",
            json={
                "name": "Starsza młodzież",
                "min_age": 12,
                "max_age": 17,
                "duration_minutes": 90,
                "id": str(uuid4()),
                "trainer_id": str(uuid4()),
            },
        )

    assert response.status_code == 422
    put_group.assert_not_awaited()


def test_put_group_replaces_all_editable_fields(client, authenticated_trainer) -> None:
    """Forward a complete mutable payload to the current trainer's service call."""
    group = _group_response()
    with patch(
        "app.api.training_groups.training_group_service.put_training_group",
        new=AsyncMock(return_value=group),
    ) as put_group:
        response = client.put(
            f"/training-groups/{GROUP_ID}",
            json={
                "name": "Starsza młodzież",
                "min_age": 12,
                "max_age": 17,
                "duration_minutes": 90,
            },
        )

    assert response.status_code == 200
    assert put_group.await_args.args[1] == TRAINER_ID
    payload = put_group.await_args.args[3]
    assert payload.model_dump() == {
        "name": "Starsza młodzież",
        "min_age": 12,
        "max_age": 17,
        "duration_minutes": 90,
    }


def test_delete_group_returns_no_content_after_success(
    client, authenticated_trainer
) -> None:
    """Return an empty successful response after removing one owned group."""
    with patch(
        "app.api.training_groups.training_group_service.delete_training_group",
        new=AsyncMock(),
    ) as delete_group:
        response = client.delete(f"/training-groups/{GROUP_ID}")

    assert response.status_code == 204
    assert response.content == b""
    assert delete_group.await_args.args[1] == TRAINER_ID


def test_delete_training_group_deletes_the_owned_group() -> None:
    """Delegate deletion of an owned group to the SQLAlchemy session."""
    session = AsyncMock()
    group = MagicMock(id=GROUP_ID)
    with patch(
        "app.db.training_groups.get_for_trainer",
        new=AsyncMock(return_value=group),
    ):
        asyncio.run(
            training_group_service.delete_training_group(session, TRAINER_ID, GROUP_ID)
        )

    session.delete.assert_awaited_once_with(group)
    session.commit.assert_awaited_once()


def test_group_and_plan_relationships_delete_orphans() -> None:
    """The model cascade removes both plans and their plan-exercise children."""
    group_plan_cascade = TrainingGroup.training_plans.property.cascade
    plan_exercise_cascade = TrainingPlan.exercises.property.cascade

    assert group_plan_cascade.delete
    assert group_plan_cascade.delete_orphan
    assert plan_exercise_cascade.delete
    assert plan_exercise_cascade.delete_orphan


def test_delete_all_trainer_groups_uses_only_the_authenticated_trainers_id(
    client, authenticated_trainer
) -> None:
    """Allow a bulk delete only when its path ID matches the OAuth trainer."""
    with patch(
        "app.api.training_groups.training_group_service.delete_all_trainer_groups",
        new=AsyncMock(),
    ) as delete_all_trainer_groups:
        response = client.delete(f"/training-groups/trainer/{TRAINER_ID}")

    assert response.status_code == 204
    delete_all_trainer_groups.assert_awaited_once()
    assert delete_all_trainer_groups.await_args.args[1] == TRAINER_ID


def test_delete_all_trainer_groups_rejects_a_different_trainers_id(
    client, authenticated_trainer
) -> None:
    """Reject a bulk delete attempt aimed at another trainer's groups."""
    with patch(
        "app.api.training_groups.training_group_service.delete_all_trainer_groups",
        new=AsyncMock(),
    ) as delete_all_trainer_groups:
        response = client.delete(f"/training-groups/trainer/{uuid4()}")

    assert response.status_code == 403
    delete_all_trainer_groups.assert_not_awaited()
