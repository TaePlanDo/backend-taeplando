"""Validation endpoint for the training-plan generation form."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.plan_generation import PlanGenerationParameters
from app.services import (
    plan_generation_candidates_service,
    plan_generation_parameters_service,
)

router = APIRouter(prefix="/plan-generation", tags=["plan-generation"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


@router.post("/parameters", response_model=None)
async def accept_parameters(
    parameters: PlanGenerationParameters,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Validate parameters and prepare candidates without persisting a plan."""

    try:
        group = await plan_generation_parameters_service.validate_parameters(
            session, current_trainer.id, parameters
        )
    except (
        plan_generation_parameters_service.InvalidPlanGenerationParametersError
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.detail,
        ) from exc
    await plan_generation_candidates_service.prepare_candidates(
        session, current_trainer.id, group, parameters
    )
    return Response(status_code=status.HTTP_200_OK)
