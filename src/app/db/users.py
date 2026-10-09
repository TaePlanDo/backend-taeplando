from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError
from app.models.enums import AuthMethod
from app.models.users import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Return the user with this email, if any."""
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Return the user with this id, if any."""
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_oauth_subject(
    session: AsyncSession, oauth_subject: str
) -> User | None:
    """Return the user linked to this OAuth subject, if any."""
    result = await session.execute(
        select(User).where(User.oauth_subject == oauth_subject)
    )
    return result.scalar_one_or_none()


async def upsert_oauth_user(
    session: AsyncSession,
    *,
    oauth_subject: str,
    email: str,
    full_name: str | None,
) -> User:
    """Create or update a Google OAuth user; raises AuthError on email clash."""
    user = await get_user_by_oauth_subject(session, oauth_subject)
    if user is None:
        await _ensure_email_available(session, email)
        user = User(
            email=email,
            full_name=full_name,
            auth_method=AuthMethod.GOOGLE,
            oauth_subject=oauth_subject,
            password_hash=None,
        )
        session.add(user)
        await session.flush()
        return user

    if user.email != email:
        await _ensure_email_available(session, email, exclude_user_id=user.id)
    user.email = email
    user.full_name = full_name
    await session.flush()
    return user


async def _ensure_email_available(
    session: AsyncSession,
    email: str,
    *,
    exclude_user_id: UUID | None = None,
) -> None:
    """Raise AuthError when the email belongs to a different user."""
    existing = await get_user_by_email(session, email)
    if existing is None:
        return
    if exclude_user_id is not None and existing.id == exclude_user_id:
        return
    raise AuthError(
        "Email already registered with a different sign-in method",
        status_code=409,
    )
