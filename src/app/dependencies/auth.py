from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.schemas.auth import UserResponse
from app.services import auth_service

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UUID:
    """Resolve the Bearer access token to its authenticated user id."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthError("Not authenticated")
    try:
        return decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise AuthError("Not authenticated") from exc


async def get_current_user(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Resolve the Bearer access token to the current user."""
    return await auth_service.get_user_response(session, user_id)
