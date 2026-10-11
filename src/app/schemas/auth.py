from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import AuthMethod


def _normalize_full_name(value: str) -> str:
    """Trim a full name and reject blank values."""
    normalized = value.strip()
    if not normalized:
        raise ValueError("Full name cannot be blank")
    return normalized


FullName = Annotated[
    str,
    Field(min_length=1, max_length=255),
    AfterValidator(_normalize_full_name),
]


class LoginRequest(BaseModel):
    """Email/password credentials for local login."""

    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(LoginRequest):
    """Payload to create a local trainer account (same credentials as login)."""

    full_name: FullName | None = None


class FullNameUpdateRequest(BaseModel):
    """New full name for the authenticated trainer."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName


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
