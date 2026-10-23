import asyncio
from datetime import UTC, datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.db import catalogs as catalogs_db
from app.db.catalogs import CatalogPage
from app.db.seed import SYSTEM_TRAINING_TYPES
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.catalogs import TrainingType
from app.models.enums import AuthMethod, CatalogVisibility
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.training_types import TrainingTypeResponse
from app.services import training_type_service

TRAINER_ID = UUID("d9aa16f7-b30a-4887-890b-247f86a2eef5")
TRAINING_TYPE_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
CREATED_AT = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


@pytest.fixture
def authenticated_trainer() -> None:
    """Authenticate training-type route tests without JWT parsing."""
    app.dependency_overrides[get_current_user] = lambda: User(
        id=TRAINER_ID,
        email="trainer@example.com",
        full_name="Trainer",
        auth_method=AuthMethod.LOCAL,
        password_hash="hash",
    )
    yield
    app.dependency_overrides.pop(get_current_user, None)


def _training_type() -> TrainingType:
    """Build one global training type for database and service tests."""
    return TrainingType(
        id=TRAINING_TYPE_ID,
        owner_user_id=None,
        name="Poomsae",
        visibility=CatalogVisibility.GLOBAL,
        created_at=CREATED_AT,
    )


def _response() -> TrainingTypeResponse:
    """Build the matching public API representation."""
    return TrainingTypeResponse(
        id=TRAINING_TYPE_ID,
        name="Poomsae",
        visibility=CatalogVisibility.GLOBAL,
        created_at=CREATED_AT,
    )


def test_list_training_types_uses_the_authenticated_trainer(
    client, authenticated_trainer
) -> None:
    """Forward pagination and the trainer ID derived from authentication."""
    response_item = _response()
    page = PaginatedResponse(
        items=[response_item], total=21, page=2, page_size=20, total_pages=2
    )
    with patch(
        "app.api.training_types.training_type_service.list_training_types",
        new=AsyncMock(return_value=page),
    ) as list_training_types:
        response = client.get("/training-types?page=2&page_size=20")

    assert response.status_code == 200
    assert response.json() == {
        "items": [response_item.model_dump(mode="json")],
        "total": 21,
        "page": 2,
        "page_size": 20,
        "total_pages": 2,
    }
    list_training_types.assert_awaited_once_with(ANY, TRAINER_ID, page=2, page_size=20)


def test_list_training_types_maps_a_database_page() -> None:
    """Map paginated training types from the database to the public API shape."""
    session = AsyncMock()
    item = _training_type()
    db_page = CatalogPage(items=[item], total=21)
    with patch(
        "app.db.catalogs.list_visible_to_trainer",
        new=AsyncMock(return_value=db_page),
    ) as list_visible_to_trainer:
        result = asyncio.run(
            training_type_service.list_training_types(
                session, TRAINER_ID, page=2, page_size=20
            )
        )

    assert result == PaginatedResponse(
        items=[_response()], total=21, page=2, page_size=20, total_pages=2
    )
    list_visible_to_trainer.assert_awaited_once_with(
        session, TRAINER_ID, catalog=TrainingType, offset=20, limit=20
    )


def test_list_training_types_filters_to_global_and_owned_entries() -> None:
    """Build one query that exposes global and trainer-owned training types only."""
    session = AsyncMock()
    result = MagicMock()
    item = _training_type()
    result.all.return_value = [(item, 1)]
    session.execute = AsyncMock(return_value=result)

    page = asyncio.run(
        catalogs_db.list_visible_to_trainer(
            session, TRAINER_ID, catalog=TrainingType, offset=0, limit=20
        )
    )

    assert page == CatalogPage(items=[item], total=1)
    statement = str(session.execute.await_args.args[0]).lower()
    assert "training_types.visibility" in statement
    assert "training_types.owner_user_id" in statement


def test_system_training_type_seed_contains_the_taekwondo_catalog() -> None:
    """Keep the globally seeded training types stable for new installations."""
    assert [training_type["name"] for training_type in SYSTEM_TRAINING_TYPES] == [
        "Technika",
        "Poomsae",
        "Walka sportowa",
        "Samoobrona",
    ]
