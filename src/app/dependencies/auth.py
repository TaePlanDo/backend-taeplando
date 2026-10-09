from typing import Annotated

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


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthError("Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise AuthError("Not authenticated") from exc
    return await auth_service.get_user_response(session, user_id)
