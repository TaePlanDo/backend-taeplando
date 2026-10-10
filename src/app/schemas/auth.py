from pydantic import BaseModel, EmailStr, Field

from app.models.enums import AuthMethod


class LoginRequest(BaseModel):
    """Email/password credentials for local login."""

    email: EmailStr
    password: str = Field(min_length=8)


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
