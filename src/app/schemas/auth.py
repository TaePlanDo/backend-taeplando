from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import AuthMethod

MAX_PASSWORD_BYTES = 72


def _validate_password_byte_length(value: str) -> str:
    """Reject passwords that bcrypt would truncate."""
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
    return value


Password = Annotated[
    str,
    Field(min_length=8),
    AfterValidator(_validate_password_byte_length),
]
PasswordAttempt = Annotated[str, AfterValidator(_validate_password_byte_length)]


class LoginRequest(BaseModel):
    """Email/password credentials for local login."""

    email: EmailStr
    password: Password


class RegisterRequest(LoginRequest):
    """Payload to create a local trainer account (same credentials as login)."""

    full_name: str | None = None


class PasswordChangeRequest(BaseModel):
    """Current and replacement password for the authenticated trainer."""

    model_config = ConfigDict(extra="forbid")

    old_password: PasswordAttempt
    new_password: Password


class TokenResponse(BaseModel):
    """Access-token payload returned by login and refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    """Public user profile returned by `/auth/me`."""

    id: str
    email: str
    full_name: str | None
    auth_method: AuthMethod
