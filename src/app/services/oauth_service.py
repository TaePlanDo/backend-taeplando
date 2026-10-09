import logging

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import Settings
from app.core.errors import AuthError
from app.db import users as users_db
from app.services.auth_service import create_auth_tokens

logger = logging.getLogger(__name__)

oauth = OAuth()
_google_oauth_initialized = False


def is_google_oauth_configured(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def init_google_oauth(settings: Settings) -> None:
    global _google_oauth_initialized
    if _google_oauth_initialized or not is_google_oauth_configured(settings):
        return
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    _google_oauth_initialized = True
    logger.info("Google OAuth client registered")


async def google_login_redirect(
    request: Request, settings: Settings
) -> RedirectResponse:
    if not is_google_oauth_configured(settings):
        raise AuthError("Google OAuth is not configured", status_code=503)
    response: RedirectResponse = await oauth.google.authorize_redirect(
        request, settings.google_redirect_uri
    )
    return response


async def complete_google_login(
    request: Request,
    session: AsyncSession,
    settings: Settings,
) -> str | None:
    """Return a new refresh token, or None when Google OAuth fails."""
    if not is_google_oauth_configured(settings):
        return None

    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as exc:
        logger.warning("Google OAuth failed: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected error during Google OAuth callback")
        return None

    userinfo = token.get("userinfo")
    if not userinfo:
        logger.warning("Google OAuth token missing userinfo")
        return None

    oauth_subject = userinfo.get("sub")
    email = userinfo.get("email")
    if not oauth_subject or not email:
        logger.warning("Google OAuth userinfo missing sub or email")
        return None

    user = await users_db.upsert_oauth_user(
        session,
        oauth_subject=oauth_subject,
        email=email,
        full_name=userinfo.get("name"),
    )
    _, plain_refresh = await create_auth_tokens(session, user.id, settings)
    return plain_refresh
