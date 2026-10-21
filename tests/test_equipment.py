import asyncio
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

from app.db import equipment as equipment_db
from app.db.equipment import EquipmentPage
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


def test_list_equipment_maps_a_database_page() -> None:
    """Map paginated equipment from the database to the public API shape."""
    session = AsyncMock()
    item = _equipment()
    db_page = EquipmentPage(items=[item], total=21)
    with patch(
        "app.db.equipment.list_visible_to_trainer",
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
        session, TRAINER_ID, offset=20, limit=20
    )


def test_create_equipment_builds_a_trainer_owned_local_entry() -> None:
    """Store new equipment as a local catalog entry owned by the trainer."""
    equipment = equipment_db.create_for_trainer(TRAINER_ID, "Tarcza treningowa")

    assert equipment.owner_user_id == TRAINER_ID
    assert equipment.name == "Tarcza treningowa"
    assert equipment.visibility == CatalogVisibility.LOCAL


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
