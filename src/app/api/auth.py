from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import Settings, get_settings
from app.core.cookies import clear_refresh_cookie, set_refresh_cookie
from app.core.errors import AuthError
from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import auth_service
from app.services.oauth_service import complete_google_login, google_login_redirect

router = APIRouter(prefix="/auth", tags=["auth"])


def _oauth_error_redirect(settings: Settings) -> RedirectResponse:
    """Redirect the browser to the SPA login page with an OAuth error flag."""
    query = urlencode({"error": "oauth"})
    return RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/login?{query}",
        status_code=status.HTTP_302_FOUND,
    )


def _set_session(
    response: Response,
    token_response: TokenResponse,
    plain_refresh: str,
    settings: Settings,
) -> TokenResponse:
    """Attach the refresh cookie and return the access-token payload."""
    set_refresh_cookie(response, plain_refresh, settings)
    return token_response


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Create a LOCAL trainer, issue tokens, and set the refresh cookie."""
    token_response, plain_refresh = await auth_service.register(
        session, body.email, body.password, body.full_name, settings
    )
    return _set_session(response, token_response, plain_refresh, settings)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Log in with email/password and set the refresh cookie."""
    token_response, plain_refresh = await auth_service.login(
        session, body.email, body.password, settings
    )
    return _set_session(response, token_response, plain_refresh, settings)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    """Rotate the refresh cookie and return a new access token."""
    refresh_value = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_value:
        raise AuthError("Invalid or expired refresh token")
    token_response, plain_refresh = await auth_service.refresh(
        session, refresh_value, settings
    )
    return _set_session(response, token_response, plain_refresh, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Revoke the refresh session and clear the refresh cookie."""
    refresh_value = request.cookies.get(settings.refresh_cookie_name)
    await auth_service.logout(session, refresh_value)
    clear_refresh_cookie(response, settings)


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: Annotated[UserResponse, Depends(get_current_user)],
) -> UserResponse:
    """Return the currently authenticated user."""
    return current_user


@router.get("/google")
async def google_login(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Start the Google OAuth login redirect."""
    return await google_login_redirect(request, settings)


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Handle the Google OAuth callback and set the refresh cookie."""
    try:
        plain_refresh = await complete_google_login(request, session, settings)
    except AuthError:
        return _oauth_error_redirect(settings)

    if plain_refresh is None:
        return _oauth_error_redirect(settings)

    response = RedirectResponse(
        url=settings.frontend_url, status_code=status.HTTP_302_FOUND
    )
    set_refresh_cookie(response, plain_refresh, settings)
    return response
