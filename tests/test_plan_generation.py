"""Coverage for asynchronous training-plan generation endpoints."""

import asyncio
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.models.catalogs import Equipment, TrainingType
from app.models.enums import PlanGenerationJobStatus
from app.models.plan_generation import PlanGenerationJob
from app.schemas.plan_generation import (
    PlanGenerationAccepted,
    PlanGenerationParameters,
    PlanGenerationStatusResponse,
)
from app.services import plan_generation_parameters_service
from app.services.plan_generation_parameters_service import (
    InvalidPlanGenerationParametersError,
)
from constants import TRAINER_ID

GROUP_ID = UUID("0ac590e1-2a46-4cb7-8944-803e364cc46b")
EQUIPMENT_ID = UUID("2ac590e1-2a46-4cb7-8944-803e364cc46b")
TRAINING_TYPE_ID = UUID("3ac590e1-2a46-4cb7-8944-803e364cc46b")
JOB_ID = UUID("4ac590e1-2a46-4cb7-8944-803e364cc46b")


def test_generation_job_is_removed_with_its_group_or_generated_plan() -> None:
    """Generation metadata must not block the existing group/plan delete flows."""

    delete_actions = {
        foreign_key.target_fullname: foreign_key.ondelete
        for foreign_key in PlanGenerationJob.__table__.foreign_keys
    }

    assert delete_actions["training_groups.id"] == "CASCADE"
    assert delete_actions["training_plans.id"] == "CASCADE"


def _payload() -> dict[str, object]:
    """Build a complete parameter request accepted by the route."""

    return {
        "training_group_id": str(GROUP_ID),
        "participant_count": 12,
        "available_equipment_ids": [str(EQUIPMENT_ID)],
        "training_type_id": str(TRAINING_TYPE_ID),
    }


def test_accept_parameters_queues_a_job_after_validation(
    client, authenticated_trainer
) -> None:
    """The form endpoint responds before the queued runner generates a plan."""

    with (
        patch(
            "app.api.plan_generation.plan_generation_parameters_service.validate_parameters",
            new=AsyncMock(),
        ) as validate_parameters,
        patch(
            "app.api.plan_generation.plan_generation_service.enqueue",
            new=AsyncMock(
                return_value=PlanGenerationAccepted(
                    id=JOB_ID, status=PlanGenerationJobStatus.QUEUED
                )
            ),
        ) as enqueue,
        patch(
            "app.api.plan_generation.plan_generation_service.run",
            new=AsyncMock(),
        ) as run,
    ):
        response = client.post("/plan-generation/parameters", json=_payload())

    assert response.status_code == 202
    assert response.json() == {"id": str(JOB_ID), "status": "QUEUED"}
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
    enqueue.assert_awaited_once_with(
        ANY,
        TRAINER_ID,
        PlanGenerationParameters(
            training_group_id=GROUP_ID,
            participant_count=12,
            available_equipment_ids=[EQUIPMENT_ID],
            training_type_id=TRAINING_TYPE_ID,
        ),
    )
    run.assert_awaited_once_with(JOB_ID)


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


def test_get_generation_status_returns_a_trainer_owned_job(
    client, authenticated_trainer
) -> None:
    """Polling exposes the status handle returned by the accepted request."""

    with patch(
        "app.api.plan_generation.plan_generation_service.get_status",
        new=AsyncMock(
            return_value=PlanGenerationStatusResponse(
                id=JOB_ID,
                status=PlanGenerationJobStatus.SUCCEEDED,
                plan_id=GROUP_ID,
                error_code=None,
                error_message=None,
            )
        ),
    ) as get_status:
        response = client.get(f"/plan-generation/{JOB_ID}")

    assert response.status_code == 200
    assert response.json() == {
        "id": str(JOB_ID),
        "status": "SUCCEEDED",
        "plan_id": str(GROUP_ID),
        "error_code": None,
        "error_message": None,
    }
    get_status.assert_awaited_once_with(ANY, TRAINER_ID, JOB_ID)


def test_get_generation_status_hides_foreign_or_missing_jobs(
    client, authenticated_trainer
) -> None:
    """Polling does not reveal another trainer's generation job."""

    with patch(
        "app.api.plan_generation.plan_generation_service.get_status",
        new=AsyncMock(return_value=None),
    ):
        response = client.get(f"/plan-generation/{JOB_ID}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Plan not found"}


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
            "app.services.plan_generation_parameters_service.training_groups_db.get_with_schema_for_trainer",
            new=AsyncMock(return_value=MagicMock()),
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


def test_validate_parameters_rejects_a_group_without_a_schema() -> None:
    """Generating an empty plan is never a valid fallback for an unfinished group."""
    session = AsyncMock()
    parameters = PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[],
        training_type_id=None,
    )
    with (
        patch(
            "app.services.plan_generation_parameters_service.training_groups_db.get_with_schema_for_trainer",
            new=AsyncMock(return_value=SimpleNamespace(schema_items=[])),
        ),
        patch(
            "app.services.plan_generation_parameters_service.catalogs_db.list_visible_by_ids",
            new=AsyncMock(),
        ) as list_visible_by_ids,
        pytest.raises(InvalidPlanGenerationParametersError, match="has no schema"),
    ):
        asyncio.run(
            plan_generation_parameters_service.validate_parameters(
                session, TRAINER_ID, parameters
            )
        )

    list_visible_by_ids.assert_not_awaited()


def test_validate_parameters_accepts_visible_non_empty_selections() -> None:
    """Return the validated resources without loading the same catalogs again."""

    session = AsyncMock()
    group = MagicMock()
    equipment = MagicMock()
    training_type = MagicMock()
    parameters = PlanGenerationParameters(
        training_group_id=GROUP_ID,
        participant_count=12,
        available_equipment_ids=[EQUIPMENT_ID],
        training_type_id=TRAINING_TYPE_ID,
    )
    with (
        patch(
            "app.services.plan_generation_parameters_service.training_groups_db.get_with_schema_for_trainer",
            new=AsyncMock(return_value=group),
        ),
        patch(
            "app.services.plan_generation_parameters_service.catalogs_db.list_visible_by_ids",
            new=AsyncMock(side_effect=[[equipment], [training_type]]),
        ) as list_visible_by_ids,
    ):
        validated_input = asyncio.run(
            plan_generation_parameters_service.validate_parameters(
                session, TRAINER_ID, parameters
            )
        )

    assert [call.kwargs["ids"] for call in list_visible_by_ids.await_args_list] == [
        [EQUIPMENT_ID],
        [TRAINING_TYPE_ID],
    ]
    assert [call.kwargs["catalog"] for call in list_visible_by_ids.await_args_list] == [
        Equipment,
        TrainingType,
    ]
    assert validated_input.group is group
    assert validated_input.equipment == [equipment]
    assert validated_input.training_types == [training_type]


@pytest.mark.parametrize(
    ("group", "catalog_results", "detail"),
    [
        (None, [], "Unknown training_group_id"),
        (True, [[]], "Unknown available_equipment_ids"),
        (True, [[MagicMock()], []], "Unknown training_type_id"),
    ],
)
def test_validate_parameters_rejects_inaccessible_resources(
    group, catalog_results, detail
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
            "app.services.plan_generation_parameters_service.training_groups_db.get_with_schema_for_trainer",
            new=AsyncMock(return_value=MagicMock() if group else None),
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
