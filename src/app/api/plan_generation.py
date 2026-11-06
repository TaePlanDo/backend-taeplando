"""Asynchronous training-plan generation endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.plan_generation import (
    PlanGenerationAccepted,
    PlanGenerationParameters,
    PlanGenerationStatusResponse,
)
from app.services import (
    plan_generation_parameters_service,
    plan_generation_service,
)

router = APIRouter(prefix="/plan-generation", tags=["plan-generation"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]


@router.post(
    "/parameters",
    response_model=PlanGenerationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def accept_parameters(
    parameters: PlanGenerationParameters,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> PlanGenerationAccepted:
    """Validate, queue, and return a handle for asynchronous plan generation."""

    try:
        await plan_generation_parameters_service.validate_parameters(
            session, current_trainer.id, parameters
        )
    except (
        plan_generation_parameters_service.InvalidPlanGenerationParametersError
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.detail,
        ) from exc
    accepted = await plan_generation_service.enqueue(
        session, current_trainer.id, parameters
    )
    background_tasks.add_task(plan_generation_service.run, accepted.id)
    return accepted


@router.get("/{job_id}", response_model=PlanGenerationStatusResponse)
async def get_generation_status(
    job_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanGenerationStatusResponse:
    """Return the current state of an asynchronous generation request."""
    generation_status = await plan_generation_service.get_status(
        session, current_trainer.id, job_id
    )
    if generation_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found"
        )
    return generation_status
