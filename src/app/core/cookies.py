from fastapi import Response

from app.core.config import Settings


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    """Attach the HttpOnly refresh cookie to the response."""
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=settings.refresh_cookie_path,
        max_age=max_age,
    )
