"""Authenticated API for a trainer's saved training plans."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.training_plan_list_filters import get_training_plan_list_filters
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.common import PaginatedResponse
from app.schemas.training_plans import (
    PlanDetail,
    PlanExerciseAlternative,
    PlanExerciseReplace,
    PlanExerciseResponse,
    PlanListItem,
    PlanStructureUpdate,
    TrainingPlanListFilters,
)
from app.services import plan_exercise_alternatives_service, training_plan_service

router = APIRouter(prefix="/training-plans", tags=["training-plans"])

CurrentTrainer = Annotated[User, Depends(get_current_user)]
PlanFilters = Annotated[
    TrainingPlanListFilters, Depends(get_training_plan_list_filters)
]


def _not_found(detail: str = "Plan not found") -> HTTPException:
    """Use one status for missing and foreign-owned resources."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get("", response_model=PaginatedResponse[PlanListItem])
async def list_plans(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    filters: PlanFilters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[PlanListItem]:
    """List one newest-first page of plans owned by the authenticated trainer."""
    return await training_plan_service.list_plans(
        session,
        current_trainer.id,
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.get("/{plan_id}", response_model=PlanDetail)
async def get_plan(
    plan_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanDetail:
    """Return one saved plan owned by the authenticated trainer."""
    try:
        return await training_plan_service.get_plan(
            session, current_trainer.id, plan_id
        )
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc


@router.patch("/{plan_id}", response_model=PlanDetail)
async def update_plan_structure(
    plan_id: UUID,
    body: PlanStructureUpdate,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanDetail:
    """Rename a plan and reorder its existing exercise slots."""
    try:
        return await training_plan_service.update_plan_structure(
            session,
            current_trainer.id,
            plan_id,
            name=body.name,
            plan_exercise_ids=body.plan_exercise_ids,
        )
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc
    except training_plan_service.PlanStructureInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.detail
        ) from exc


@router.put(
    "/{plan_id}/exercises/{plan_exercise_id}",
    response_model=PlanExerciseResponse,
)
async def replace_plan_exercise(
    plan_id: UUID,
    plan_exercise_id: UUID,
    body: PlanExerciseReplace,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PlanExerciseResponse:
    """Replace one exercise slot in a saved plan owned by the trainer."""
    try:
        return await training_plan_service.replace_plan_exercise(
            session,
            current_trainer.id,
            plan_id,
            plan_exercise_id,
            body.exercise_id,
        )
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc


@router.delete(
    "/{plan_id}/exercises/{plan_exercise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_plan_exercise(
    plan_id: UUID,
    plan_exercise_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete one exercise slot from a saved plan owned by the trainer."""
    try:
        await training_plan_service.delete_plan_exercise(
            session, current_trainer.id, plan_id, plan_exercise_id
        )
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{plan_id}/exercises/{plan_exercise_id}/alternatives",
    response_model=list[PlanExerciseAlternative],
)
async def list_plan_exercise_alternatives(
    plan_id: UUID,
    plan_exercise_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[PlanExerciseAlternative]:
    """Rank hard-filtered alternatives for one exercise slot in a saved plan."""
    try:
        return await plan_exercise_alternatives_service.list_alternatives(
            session,
            current_trainer.id,
            plan_id,
            plan_exercise_id,
            limit=limit,
        )
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete one saved plan owned by the authenticated trainer."""
    try:
        await training_plan_service.delete_plan(session, current_trainer.id, plan_id)
    except training_plan_service.PlanResourceNotFoundError as exc:
        raise _not_found(exc.detail) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
