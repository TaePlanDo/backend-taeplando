from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import AuthMethod

MAX_PASSWORD_BYTES = 72


def _validate_password_byte_length(value: str) -> str:
    """Reject passwords that bcrypt would truncate."""
    if len(value.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes long")
    return value


def _validate_password_complexity(value: str) -> str:
    """Require letter, digit, and special character (local auth policy)."""
    if not any(char.isalpha() for char in value):
        raise ValueError("Password must contain at least one letter")
    if not any(char.isdigit() for char in value):
        raise ValueError("Password must contain at least one digit")
    if all(char.isalnum() for char in value):
        raise ValueError("Password must contain at least one special character")
    return value


# Presented at login — length only (legacy hashes may be weaker).
LoginPassword = Annotated[
    str,
    Field(min_length=8),
    AfterValidator(_validate_password_byte_length),
]

# Set on register / password change — full local-auth policy.
Password = Annotated[
    str,
    Field(min_length=8),
    AfterValidator(_validate_password_byte_length),
    AfterValidator(_validate_password_complexity),
]
PasswordAttempt = Annotated[str, AfterValidator(_validate_password_byte_length)]


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
    password: LoginPassword


class RegisterRequest(BaseModel):
    """Payload to create a local trainer account."""

    email: EmailStr
    password: Password
    full_name: FullName | None = None


class FullNameUpdateRequest(BaseModel):
    """New full name for the authenticated trainer."""

    model_config = ConfigDict(extra="forbid")

    full_name: FullName


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
