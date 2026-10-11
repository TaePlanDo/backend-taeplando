from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import AuthMethod


class LoginRequest(BaseModel):
    """Email/password credentials for local login."""

    email: EmailStr
    password: str = Field(min_length=8)


class RegisterRequest(LoginRequest):
    """Payload to create a local trainer account (same credentials as login)."""

    full_name: str | None = None


class UserProfileUpdateRequest(BaseModel):
    """Complete editable profile data for the authenticated trainer."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: str | None = Field(max_length=255)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        """Store blank names as absent profile data."""
        if value is None:
            return None
        return value.strip() or None


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
