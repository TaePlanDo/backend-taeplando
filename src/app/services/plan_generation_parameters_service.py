"""Validate training-plan parameters without generation side effects."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import catalogs as catalogs_db
from app.db import training_groups as training_groups_db
from app.models.catalogs import Equipment, TrainingType
from app.schemas.plan_generation import PlanGenerationParameters


class InvalidPlanGenerationParametersError(Exception):
    """Raised when a selected generation parameter is inaccessible or absent."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


async def validate_parameters(
    session: AsyncSession,
    trainer_id: UUID,
    parameters: PlanGenerationParameters,
) -> None:
    """Verify a trainer can use the supplied parameters in a future generation step."""

    group = await training_groups_db.get_for_trainer(
        session, trainer_id, parameters.training_group_id
    )
    if group is None:
        raise InvalidPlanGenerationParametersError("Unknown training_group_id")

    equipment = await catalogs_db.list_visible_by_ids(
        session,
        trainer_id,
        catalog=Equipment,
        ids=parameters.available_equipment_ids,
    )
    if len(equipment) != len(parameters.available_equipment_ids):
        raise InvalidPlanGenerationParametersError("Unknown available_equipment_ids")

    if parameters.training_type_id is None:
        return

    training_types = await catalogs_db.list_visible_by_ids(
        session,
        trainer_id,
        catalog=TrainingType,
        ids=[parameters.training_type_id],
    )
    if not training_types:
        raise InvalidPlanGenerationParametersError("Unknown training_type_id")
