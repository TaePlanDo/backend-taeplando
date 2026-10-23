import asyncio
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from app.db import equipment as equipment_db
from app.db.catalogs import CatalogPage
from app.models.catalogs import Equipment
from app.models.enums import CatalogVisibility
from app.schemas.common import PaginatedResponse
from app.schemas.equipment import EquipmentResponse, EquipmentWrite
from app.services import equipment_service
from constants import TRAINER_ID

EQUIPMENT_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
CREATED_AT = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _equipment_response() -> EquipmentResponse:
    """Build one complete equipment response used by route tests."""
    return EquipmentResponse(
        id=EQUIPMENT_ID,
        name="Tarcza treningowa",
        visibility=CatalogVisibility.LOCAL,
        created_at=CREATED_AT,
    )


def _equipment() -> Equipment:
    """Build one persisted equipment object for service tests."""
    return Equipment(
        id=EQUIPMENT_ID,
        owner_user_id=TRAINER_ID,
        name="Tarcza treningowa",
        visibility=CatalogVisibility.LOCAL,
        created_at=CREATED_AT,
    )


def test_list_equipment_returns_a_page_for_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Forward pagination and the trainer ID derived from authentication."""
    response_item = _equipment_response()
    page = PaginatedResponse(
        items=[response_item], total=21, page=2, page_size=20, total_pages=2
    )
    with patch(
        "app.api.equipment.equipment_service.list_equipment",
        new=AsyncMock(return_value=page),
    ) as list_equipment:
        response = client.get("/equipment?page=2&page_size=20")

    assert response.status_code == 200
    assert response.json() == {
        "items": [response_item.model_dump(mode="json")],
        "total": 21,
        "page": 2,
        "page_size": 20,
        "total_pages": 2,
    }
    list_equipment.assert_awaited_once_with(ANY, TRAINER_ID, page=2, page_size=20)


def test_create_equipment_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Create equipment for the trainer from authentication, never from the body."""
    response_item = _equipment_response()
    with patch(
        "app.api.equipment.equipment_service.create_equipment",
        new=AsyncMock(return_value=response_item),
    ) as create_equipment:
        response = client.post("/equipment", json={"name": "  Tarcza treningowa  "})

    assert response.status_code == 201
    assert response.json() == response_item.model_dump(mode="json")
    payload = create_equipment.await_args.args[2]
    assert create_equipment.await_args.args[1] == TRAINER_ID
    assert payload.name == "Tarcza treningowa"


def test_create_equipment_rejects_invalid_payload(
    client, authenticated_trainer
) -> None:
    """Reject whitespace-only names and fields outside the creation contract."""
    with patch(
        "app.api.equipment.equipment_service.create_equipment", new=AsyncMock()
    ) as create_equipment:
        blank = client.post("/equipment", json={"name": "   "})
        extra_field = client.post(
            "/equipment", json={"name": "Tarcza", "owner_user_id": str(TRAINER_ID)}
        )

    assert blank.status_code == 422
    assert extra_field.status_code == 422
    create_equipment.assert_not_awaited()


def test_update_equipment_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Rename only equipment owned by the authenticated trainer."""
    response_item = _equipment_response()
    with patch(
        "app.api.equipment.equipment_service.update_equipment",
        new=AsyncMock(return_value=response_item),
    ) as update_equipment:
        response = client.put(f"/equipment/{EQUIPMENT_ID}", json={"name": "  Tarcza  "})

    assert response.status_code == 200
    assert response.json() == response_item.model_dump(mode="json")
    assert update_equipment.await_args.args[1:3] == (TRAINER_ID, EQUIPMENT_ID)
    assert update_equipment.await_args.args[3] == EquipmentWrite(name="Tarcza")


def test_update_equipment_rejects_non_editable_fields(
    client, authenticated_trainer
) -> None:
    """Reject ownership and visibility changes outside the API contract."""
    with patch(
        "app.api.equipment.equipment_service.update_equipment", new=AsyncMock()
    ) as update_equipment:
        response = client.put(
            f"/equipment/{EQUIPMENT_ID}",
            json={"name": "Tarcza", "visibility": "GLOBAL"},
        )

    assert response.status_code == 422
    update_equipment.assert_not_awaited()


def test_update_equipment_hides_foreign_or_global_equipment(
    client, authenticated_trainer
) -> None:
    """Use one not-found response for equipment that cannot be changed."""
    with patch(
        "app.api.equipment.equipment_service.update_equipment",
        new=AsyncMock(side_effect=equipment_service.EquipmentNotFoundError),
    ):
        response = client.put(f"/equipment/{EQUIPMENT_ID}", json={"name": "Tarcza"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment not found"}


def test_delete_equipment_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Delete only equipment owned by the authenticated trainer."""
    with patch(
        "app.api.equipment.equipment_service.delete_equipment", new=AsyncMock()
    ) as delete_equipment:
        response = client.delete(f"/equipment/{EQUIPMENT_ID}")

    assert response.status_code == 204
    delete_equipment.assert_awaited_once_with(ANY, TRAINER_ID, EQUIPMENT_ID)


def test_delete_equipment_hides_foreign_or_global_equipment(
    client, authenticated_trainer
) -> None:
    """Use one not-found response for equipment that cannot be deleted."""
    with patch(
        "app.api.equipment.equipment_service.delete_equipment",
        new=AsyncMock(side_effect=equipment_service.EquipmentNotFoundError),
    ):
        response = client.delete(f"/equipment/{EQUIPMENT_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Equipment not found"}


def test_list_equipment_maps_a_database_page() -> None:
    """Map paginated equipment from the database to the public API shape."""
    session = AsyncMock()
    item = _equipment()
    db_page = CatalogPage(items=[item], total=21)
    with patch(
        "app.db.catalogs.list_visible_to_trainer",
        new=AsyncMock(return_value=db_page),
    ) as list_visible_to_trainer:
        result = asyncio.run(
            equipment_service.list_equipment(session, TRAINER_ID, page=2, page_size=20)
        )

    assert result == PaginatedResponse(
        items=[_equipment_response()],
        total=21,
        page=2,
        page_size=20,
        total_pages=2,
    )
    list_visible_to_trainer.assert_awaited_once_with(
        session, TRAINER_ID, catalog=Equipment, offset=20, limit=20
    )


def test_create_equipment_builds_a_trainer_owned_local_entry() -> None:
    """Store new equipment as a local catalog entry owned by the trainer."""
    equipment = equipment_db.create_for_trainer(TRAINER_ID, "Tarcza treningowa")

    assert equipment.owner_user_id == TRAINER_ID
    assert equipment.name == "Tarcza treningowa"
    assert equipment.visibility == CatalogVisibility.LOCAL


def test_get_local_for_trainer_scopes_by_owner_and_visibility() -> None:
    """Look up mutable equipment only in the trainer's local catalog."""
    session = AsyncMock()
    result = MagicMock()
    item = _equipment()
    result.scalar_one_or_none.return_value = item
    session.execute = AsyncMock(return_value=result)

    found = asyncio.run(
        equipment_db.get_local_for_trainer(session, TRAINER_ID, EQUIPMENT_ID)
    )

    assert found is item
    statement = session.execute.await_args.args[0]
    assert set(statement.compile().params.values()) == {
        EQUIPMENT_ID,
        TRAINER_ID,
        CatalogVisibility.LOCAL,
    }


def test_create_equipment_commits_the_new_entry() -> None:
    """Add the new entry and commit it in the service layer."""
    session = MagicMock()
    session.commit = AsyncMock()
    item = _equipment()
    payload = EquipmentWrite(name="Tarcza treningowa")
    with patch("app.db.equipment.create_for_trainer", return_value=item):
        result = asyncio.run(
            equipment_service.create_equipment(session, TRAINER_ID, payload)
        )

    assert result == _equipment_response()
    session.add.assert_called_once_with(item)
    session.commit.assert_awaited_once()


def test_update_equipment_renames_an_owned_local_entry() -> None:
    """Persist a new name only for the trainer's local equipment."""
    session = MagicMock()
    session.commit = AsyncMock()
    item = _equipment()
    with patch(
        "app.db.equipment.get_local_for_trainer",
        new=AsyncMock(return_value=item),
    ) as get_local_for_trainer:
        result = asyncio.run(
            equipment_service.update_equipment(
                session, TRAINER_ID, EQUIPMENT_ID, EquipmentWrite(name="Tarcza")
            )
        )

    assert result == EquipmentResponse(
        id=EQUIPMENT_ID,
        name="Tarcza",
        visibility=CatalogVisibility.LOCAL,
        created_at=CREATED_AT,
    )
    get_local_for_trainer.assert_awaited_once_with(session, TRAINER_ID, EQUIPMENT_ID)
    session.commit.assert_awaited_once()


def test_delete_equipment_removes_an_owned_local_entry() -> None:
    """Delete the local equipment row in the service layer."""
    session = MagicMock()
    session.delete = AsyncMock()
    session.commit = AsyncMock()
    item = _equipment()
    with patch(
        "app.db.equipment.get_local_for_trainer",
        new=AsyncMock(return_value=item),
    ):
        asyncio.run(
            equipment_service.delete_equipment(session, TRAINER_ID, EQUIPMENT_ID)
        )

    session.delete.assert_awaited_once_with(item)
    session.commit.assert_awaited_once()
