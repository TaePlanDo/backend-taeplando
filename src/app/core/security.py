import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import Settings


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return True if the password matches the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode(),
        password_hash.encode(),
    )


def hash_password(plain_password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(plain_password.encode(), bcrypt.gensalt()).decode()


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    """Create a signed access JWT and its lifetime in seconds."""
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
    """Validate an access JWT and return the subject user id."""
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
    """Generate a high-entropy opaque refresh token."""
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage (SHA-256)."""
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_token_expires_at(settings: Settings) -> datetime:
    """Return the absolute expiry time for a new refresh token."""
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
