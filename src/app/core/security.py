import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import Settings


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode(),
        password_hash.encode(),
    )


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "exp": now + expires_delta,
        "iat": now,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str, settings: Settings) -> UUID:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise jwt.InvalidTokenError("Missing subject")
    return UUID(sub)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expires_at(settings: Settings) -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
