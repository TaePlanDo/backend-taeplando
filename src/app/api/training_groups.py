"""Authenticated API for a trainer's training groups."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import UserResponse
from app.schemas.training import (
    TrainingGroupResponse,
    TrainingGroupWrite,
)
from app.services import training_group_service

router = APIRouter(prefix="/training-groups", tags=["training-groups"])


def get_current_trainer_id(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UUID:
    """Convert the authenticated user's public string ID to a UUID."""
    return UUID(current_user.id)


CurrentTrainerId = Annotated[UUID, Depends(get_current_trainer_id)]


def _not_found() -> HTTPException:
    """Use one response for missing and foreign-owned groups."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
    )


def _ensure_current_trainer(trainer_id: UUID, current_trainer_id: UUID) -> None:
    """Ensure a bulk delete cannot target another trainer's groups."""
    if trainer_id != current_trainer_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot manage another trainer's groups",
        )


@router.get("", response_model=list[TrainingGroupResponse])
async def list_groups(
    trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
    duration_minutes: Annotated[int | None, Query(gt=0)] = None,
    min_age: Annotated[int | None, Query(gt=0)] = None,
    max_age: Annotated[int | None, Query(gt=0)] = None,
) -> list[TrainingGroupResponse]:
    """List and optionally filter groups belonging to the authenticated trainer."""
    return await training_group_service.list_training_groups(
        session,
        trainer_id,
        duration_minutes=duration_minutes,
        min_age=min_age,
        max_age=max_age,
    )


@router.post(
    "", response_model=TrainingGroupResponse, status_code=status.HTTP_201_CREATED
)
async def create_group(
    payload: TrainingGroupWrite,
    trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingGroupResponse:
    """Create a group with the default 100% main-part schema."""
    return await training_group_service.create_training_group(
        session, trainer_id, payload
    )


@router.get("/{group_id}", response_model=TrainingGroupResponse)
async def get_group(
    group_id: UUID,
    trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingGroupResponse:
    """Return one group owned by the authenticated trainer."""
    try:
        return await training_group_service.get_training_group(
            session, trainer_id, group_id
        )
    except training_group_service.TrainingGroupNotFoundError as exc:
        raise _not_found() from exc


@router.put("/{group_id}", response_model=TrainingGroupResponse)
async def put_group(
    group_id: UUID,
    payload: TrainingGroupWrite,
    trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TrainingGroupResponse:
    """Replace all editable fields of a group owned by the authenticated trainer."""
    try:
        return await training_group_service.put_training_group(
            session, trainer_id, group_id, payload
        )
    except training_group_service.TrainingGroupNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/trainer/{trainer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_groups(
    trainer_id: UUID,
    current_trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete all groups of the OAuth-authenticated trainer named in the path."""
    _ensure_current_trainer(trainer_id, current_trainer_id)
    await training_group_service.delete_all_trainer_training_groups(
        session, current_trainer_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    trainer_id: CurrentTrainerId,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete an owned group together with its dependent historical plans."""
    try:
        await training_group_service.delete_training_group(
            session, trainer_id, group_id
        )
    except training_group_service.TrainingGroupNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
