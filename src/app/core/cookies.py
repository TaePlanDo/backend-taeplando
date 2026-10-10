from typing import Any

from fastapi import Response

from app.core.config import Settings


def _refresh_cookie_params(settings: Settings) -> dict[str, Any]:
    """Shared cookie attributes for set and clear (must stay in sync)."""
    return {
        "key": settings.refresh_cookie_name,
        "path": settings.refresh_cookie_path,
        "secure": settings.refresh_cookie_secure,
        "httponly": True,
        "samesite": "lax",
    }


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    """Attach the HttpOnly refresh cookie to the response."""
    max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        value=token,
        max_age=max_age,
        **_refresh_cookie_params(settings),
    )


def clear_refresh_cookie(response: Response, settings: Settings) -> None:
    """Remove the refresh cookie (same path/flags as set)."""
    response.delete_cookie(**_refresh_cookie_params(settings))
