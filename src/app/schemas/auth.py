from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import AuthMethod


class LoginRequest(BaseModel):
    """Email/password credentials for local login."""

    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(LoginRequest):
    """Payload to create a local trainer account (same credentials as login)."""

    full_name: str | None = None


class FullNameUpdateRequest(BaseModel):
    """New full name for the authenticated trainer."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        """Reject names consisting only of whitespace."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Full name cannot be blank")
        return normalized


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
