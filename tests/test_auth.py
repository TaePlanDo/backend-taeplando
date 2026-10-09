import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from starlette.responses import RedirectResponse, Response

from app.core.config import Settings
from app.core.cookies import set_refresh_cookie
from app.core.errors import AuthError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db import users as users_db
from app.models.enums import AuthMethod
from app.models.users import RefreshToken, User


def _local_user(*, password: str = "password123") -> User:
    return User(
        id=uuid4(),
        email="trainer@example.com",
        full_name="Trainer",
        auth_method=AuthMethod.LOCAL,
        password_hash=hash_password(password),
    )


def test_login_validation_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "longenough"},
    )
    assert response.status_code == 422


def test_login_validation_short_password(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "trainer@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_login_success_sets_cookie(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    with patch(
        "app.db.users.get_user_by_email",
        new=AsyncMock(return_value=user),
    ):
        response = client.post(
            "/auth/login",
            json={"email": user.email, "password": "password123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert decode_access_token(body["access_token"], override_settings) == user.id
    assert "refresh_token=" in response.headers.get("set-cookie", "")


def test_login_invalid_credentials(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    with patch(
        "app.db.users.get_user_by_email",
        new=AsyncMock(return_value=user),
    ):
        response = client.post(
            "/auth/login",
            json={"email": user.email, "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


def test_refresh_without_cookie_returns_401(
    client: TestClient, override_settings: Settings
) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"


def test_refresh_rotates_token(
    client: TestClient, override_settings: Settings
) -> None:
    user_id = uuid4()
    plain = "current-refresh-token"
    record = RefreshToken(
        id=uuid4(),
        user_id=user_id,
        token_hash=hash_refresh_token(plain),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    client.cookies.set(
        override_settings.refresh_cookie_name,
        plain,
        path=override_settings.refresh_cookie_path,
    )

    with (
        patch(
            "app.db.refresh_tokens.get_refresh_token_by_hash",
            new=AsyncMock(return_value=record),
        ),
        patch(
            "app.db.refresh_tokens.revoke_refresh_token",
            new=AsyncMock(),
        ),
        patch(
            "app.db.refresh_tokens.create_refresh_token",
            new=AsyncMock(),
        ),
    ):
        response = client.post("/auth/refresh")

    assert response.status_code == 200
    body = response.json()
    assert decode_access_token(body["access_token"], override_settings) == user_id
    assert "refresh_token=" in response.headers.get("set-cookie", "")


def test_refresh_rejects_unknown_token(
    client: TestClient, override_settings: Settings
) -> None:
    client.cookies.set(
        override_settings.refresh_cookie_name,
        "missing",
        path=override_settings.refresh_cookie_path,
    )
    with patch(
        "app.db.refresh_tokens.get_refresh_token_by_hash",
        new=AsyncMock(return_value=None),
    ):
        response = client.post("/auth/refresh")

    assert response.status_code == 401


def test_me_without_bearer_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_with_valid_jwt(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)

    with patch(
        "app.db.users.get_user_by_id",
        new=AsyncMock(return_value=user),
    ):
        response = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user.email
    assert data["auth_method"] == "LOCAL"


def test_jwt_create_and_decode(test_settings: Settings) -> None:
    user_id = uuid4()
    token, expires_in = create_access_token(user_id, test_settings)
    assert expires_in == 15 * 60
    assert decode_access_token(token, test_settings) == user_id


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("password123")
    assert verify_password("password123", hashed)
    assert not verify_password("nope", hashed)


def test_refresh_cookie_attributes(test_settings: Settings) -> None:
    response = Response()
    set_refresh_cookie(response, "refresh-value", test_settings)
    cookie_header = response.headers.get("set-cookie", "")
    assert "refresh_token=refresh-value" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Path=/auth/refresh" in cookie_header
    assert "SameSite=lax" in cookie_header


def test_google_login_unconfigured_returns_503(
    client: TestClient, override_settings: Settings
) -> None:
    response = client.get("/auth/google")
    assert response.status_code == 503
    assert response.json()["detail"] == "Google OAuth is not configured"


def test_google_login_redirect_when_configured(
    client: TestClient, override_settings: Settings
) -> None:
    override_settings.google_client_id = "client-id"
    override_settings.google_client_secret = "secret"
    redirect = RedirectResponse(url="https://accounts.google.com/", status_code=302)

    with patch(
        "app.api.auth.google_login_redirect",
        new=AsyncMock(return_value=redirect),
    ):
        response = client.get("/auth/google", follow_redirects=False)

    assert response.status_code == 302


def test_google_callback_success_sets_cookie(
    client: TestClient, override_settings: Settings
) -> None:
    with patch(
        "app.api.auth.complete_google_login",
        new=AsyncMock(return_value="new-refresh"),
    ):
        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == override_settings.frontend_url
    assert "refresh_token=new-refresh" in response.headers.get("set-cookie", "")


def test_google_callback_failure_redirects_with_error(
    client: TestClient, override_settings: Settings
) -> None:
    with patch(
        "app.api.auth.complete_google_login",
        new=AsyncMock(return_value=None),
    ):
        response = client.get("/auth/google/callback", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"] == (
        f"{override_settings.frontend_url}/login?error=oauth"
    )


def test_upsert_oauth_user_rejects_email_collision() -> None:
    existing = User(
        id=uuid4(),
        email="taken@example.com",
        full_name="Local",
        auth_method=AuthMethod.LOCAL,
        password_hash="hash",
    )
    session = AsyncMock()

    async def _run() -> None:
        with (
            patch(
                "app.db.users.get_user_by_oauth_subject",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.db.users.get_user_by_email",
                new=AsyncMock(return_value=existing),
            ),
        ):
            try:
                await users_db.upsert_oauth_user(
                    session,
                    oauth_subject="google-sub",
                    email="taken@example.com",
                    full_name="Google User",
                )
            except AuthError as exc:
                assert exc.status_code == 409
                return
            raise AssertionError("expected AuthError")

    asyncio.run(_run())
