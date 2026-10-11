"""Authenticated API for a trainer's groups."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.users import User
from app.schemas.training import (
    GroupResponse,
    GroupWrite,
)
from app.services import training_group_service

router = APIRouter(prefix="/training-groups", tags=["training-groups"])


CurrentTrainer = Annotated[User, Depends(get_current_user)]


def _not_found() -> HTTPException:
    """Use one response for missing and foreign-owned groups."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Group not found"
    )


@router.get("", response_model=list[GroupResponse])
async def list_groups(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
    duration_minutes: Annotated[int | None, Query(gt=0)] = None,
    min_age: Annotated[int, Query(ge=0)] = 0,
    max_age: Annotated[int, Query(gt=0)] = 99,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[GroupResponse]:
    """List a page of groups owned by the authenticated trainer."""
    if min_age > max_age:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="min_age must be less than or equal to max_age",
        )
    return await training_group_service.list_groups(
        session,
        current_trainer.id,
        duration_minutes=duration_minutes,
        min_age=min_age,
        max_age=max_age,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupWrite,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    """Create a group with the default 100% main-part schema."""
    return await training_group_service.create_group(
        session, current_trainer.id, payload
    )


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    """Return one group owned by the authenticated trainer."""
    try:
        return await training_group_service.get_group(
            session, current_trainer.id, group_id
        )
    except training_group_service.GroupNotFoundError as exc:
        raise _not_found() from exc


@router.put("/{group_id}", response_model=GroupResponse)
async def put_group(
    group_id: UUID,
    payload: GroupWrite,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> GroupResponse:
    """Replace all editable fields of a group owned by the authenticated trainer."""
    try:
        return await training_group_service.put_group(
            session, current_trainer.id, group_id, payload
        )
    except training_group_service.GroupNotFoundError as exc:
        raise _not_found() from exc


@router.delete("/trainer", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_trainer_groups(
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete all groups belonging to the OAuth-authenticated trainer."""
    await training_group_service.delete_all_trainer_groups(session, current_trainer.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: UUID,
    current_trainer: CurrentTrainer,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Delete an owned group together with its dependent historical plans."""
    try:
        await training_group_service.delete_group(session, current_trainer.id, group_id)
    except training_group_service.GroupNotFoundError as exc:
        raise _not_found() from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
