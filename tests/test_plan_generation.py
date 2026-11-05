"""Coverage for accepting training-plan generation parameters."""

import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.catalogs import Equipment, TrainingType
from app.schemas.plan_generation import PlanGenerationParameters
from app.services import plan_generation_parameters_service
from app.services.plan_generation_parameters_service import (
    InvalidPlanGenerationParametersError,
)
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
EQUIPMENT_ID = UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b")
TRAINING_TYPE_ID = UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b")


def _payload() -> dict[str, object]:
    """Build a complete parameter request accepted by the route."""

    return {
        "training_group_id": str(GROUP_ID),
        "participant_count": 12,
        "available_equipment_ids": [str(EQUIPMENT_ID)],
        "training_type_id": str(TRAINING_TYPE_ID),
    }


def test_accept_parameters_returns_an_empty_ok_response(
    client, authenticated_trainer
) -> None:
    """The form endpoint validates input but neither persists nor generates a plan."""

    with patch(
        "app.api.plan_generation.plan_generation_parameters_service.validate_parameters",
        new=AsyncMock(),
    ) as validate_parameters:
        response = client.post("/plan-generation/parameters", json=_payload())

    assert response.status_code == 200
    assert response.content == b""
    validate_parameters.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PlanGenerationParameters(
            training_group_id=GROUP_ID,
            participant_count=12,
            available_equipment_ids=[EQUIPMENT_ID],
            training_type_id=TRAINING_TYPE_ID,
        ),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {**_payload(), "participant_count": 0},
        {**_payload(), "available_equipment_ids": [str(EQUIPMENT_ID)] * 2},
        {**_payload(), "unexpected": True},
    ],
)
def test_accept_parameters_rejects_invalid_request_shapes(
    client, authenticated_trainer, payload
) -> None:
    """Reject malformed form data before the validation service is invoked."""

    with patch(
        "app.api.plan_generation.plan_generation_parameters_service.validate_parameters",
        new=AsyncMock(),
    ) as validate_parameters:
        response = client.post("/plan-generation/parameters", json=payload)

    assert response.status_code == 422
    validate_parameters.assert_not_awaited()


def test_accept_parameters_returns_validation_errors_from_the_service(
    client, authenticated_trainer
) -> None:
    """Expose inaccessible resources as request validation failures."""

    with patch(
        "app.api.plan_generation.plan_generation_parameters_service.validate_parameters",
        new=AsyncMock(
            side_effect=InvalidPlanGenerationParametersError(
                "Unknown training_group_id"
            )
        ),
    ):
        response = client.post("/plan-generation/parameters", json=_payload())

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown training_group_id"}


def test_validate_parameters_allows_an_empty_equipment_list_and_auto_type() -> None:
    """No equipment and no explicit type are both valid generation inputs."""

    session = AsyncMock()
    parameters = PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[],
        training_type_id=None,
    )
    with (
        patch(
            "app.services.plan_generation_parameters_service.training_groups_db.exists_for_trainer",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.plan_generation_parameters_service.catalogs_db.list_visible_by_ids",
            new=AsyncMock(return_value=[]),
        ) as list_visible_by_ids,
    ):
        asyncio.run(
            plan_generation_parameters_service.validate_parameters(
                session, TRAINER_ID, parameters
            )
        )

    list_visible_by_ids.assert_awaited_once()
    assert list_visible_by_ids.await_args.kwargs["ids"] == []


def test_validate_parameters_accepts_visible_non_empty_selections() -> None:
    """Validate every selected catalog item before accepting the form."""

    session = AsyncMock()
    parameters = PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[EQUIPMENT_ID],
        training_type_id=TRAINING_TYPE_ID,
    )
    with (
        patch(
            "app.services.plan_generation_parameters_service.training_groups_db.exists_for_trainer",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.services.plan_generation_parameters_service.catalogs_db.list_visible_by_ids",
            new=AsyncMock(side_effect=[[MagicMock()], [MagicMock()]]),
        ) as list_visible_by_ids,
    ):
        asyncio.run(
            plan_generation_parameters_service.validate_parameters(
                session, TRAINER_ID, parameters
            )
        )

    assert [
        call.kwargs["ids"] for call in list_visible_by_ids.await_args_list
    ] == [[EQUIPMENT_ID], [TRAINING_TYPE_ID]]
    assert [
        call.kwargs["catalog"] for call in list_visible_by_ids.await_args_list
    ] == [Equipment, TrainingType]


@pytest.mark.parametrize(
    ("group_exists", "catalog_results", "detail"),
    [
        (False, [], "Unknown training_group_id"),
        (True, [[]], "Unknown available_equipment_ids"),
        (True, [[MagicMock()], []], "Unknown training_type_id"),
    ],
)
def test_validate_parameters_rejects_inaccessible_resources(
    group_exists, catalog_results, detail
) -> None:
    """Do not accept a foreign or missing group, equipment, or training type."""

    session = AsyncMock()
    parameters = PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[EQUIPMENT_ID],
        training_type_id=TRAINING_TYPE_ID,
    )
    with (
        patch(
            "app.services.plan_generation_parameters_service.training_groups_db.exists_for_trainer",
            new=AsyncMock(return_value=group_exists),
        ),
        patch(
            "app.services.plan_generation_parameters_service.catalogs_db.list_visible_by_ids",
            new=AsyncMock(side_effect=catalog_results),
        ),
        pytest.raises(InvalidPlanGenerationParametersError, match=detail),
    ):
        asyncio.run(
            plan_generation_parameters_service.validate_parameters(
                session, TRAINER_ID, parameters
            )
        )
