import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.sql.dml import Delete
from starlette.responses import RedirectResponse, Response

from app.core.config import Settings
from app.core.cookies import clear_refresh_cookie, set_refresh_cookie
from app.core.errors import AuthError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.db import users as users_db
from app.db.refresh_tokens import consume_refresh_token, delete_refresh_tokens_for_user
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


def test_register_validation_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "longenough"},
    )
    assert response.status_code == 422


def test_register_validation_short_password(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "trainer@example.com", "password": "short"},
    )
    assert response.status_code == 422


def test_register_rejects_invalid_full_name(client: TestClient) -> None:
    for full_name in ("   ", "a" * 256):
        response = client.post(
            "/auth/register",
            json={
                "email": "trainer@example.com",
                "password": "password123",
                "full_name": full_name,
            },
        )

        assert response.status_code == 422


def test_register_success_sets_cookie(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    create_user = AsyncMock(return_value=user)
    with patch(
        "app.db.users.create_local_user",
        new=create_user,
    ):
        response = client.post(
            "/auth/register",
            json={
                "email": user.email,
                "password": "password123",
                "full_name": "  Trainer  ",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert decode_access_token(body["access_token"], override_settings) == user.id
    assert "refresh_token=" in response.headers.get("set-cookie", "")
    assert create_user.await_args.kwargs["full_name"] == "Trainer"


def test_register_duplicate_email_returns_409(
    client: TestClient, override_settings: Settings
) -> None:
    with patch(
        "app.db.users.create_local_user",
        new=AsyncMock(
            side_effect=AuthError("Email already registered", status_code=409)
        ),
    ):
        response = client.post(
            "/auth/register",
            json={"email": "taken@example.com", "password": "password123"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_refresh_without_cookie_returns_401(
    client: TestClient, override_settings: Settings
) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"


def test_refresh_rotates_token(client: TestClient, override_settings: Settings) -> None:
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
            "app.db.refresh_tokens.consume_refresh_token",
            new=AsyncMock(return_value=record),
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
        "app.db.refresh_tokens.consume_refresh_token",
        new=AsyncMock(return_value=None),
    ):
        response = client.post("/auth/refresh")

    assert response.status_code == 401


def test_logout_without_cookie_clears_cookie(
    client: TestClient, override_settings: Settings
) -> None:
    response = client.post("/auth/logout")
    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie", "")
    assert override_settings.refresh_cookie_name in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


def test_logout_revokes_refresh_token(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    plain = "logout-refresh-token"
    token_hash = hash_refresh_token(plain)
    client.cookies.set(
        override_settings.refresh_cookie_name,
        plain,
        path=override_settings.refresh_cookie_path,
    )
    consume = AsyncMock(
        return_value=RefreshToken(
            id=uuid4(),
            user_id=uuid4(),
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )

    with patch("app.db.refresh_tokens.consume_refresh_token", new=consume):
        response = client.post("/auth/logout")

    assert response.status_code == 204
    consume.assert_awaited_once_with(db_session, token_hash)
    db_session.commit.assert_awaited()


def test_logout_with_invalid_cookie_clears_cookie(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    client.cookies.set(
        override_settings.refresh_cookie_name,
        "not-a-valid-refresh-token",
        path=override_settings.refresh_cookie_path,
    )
    consume = AsyncMock(return_value=None)

    with patch("app.db.refresh_tokens.consume_refresh_token", new=consume):
        response = client.post("/auth/logout")

    assert response.status_code == 204
    consume.assert_awaited_once()
    db_session.commit.assert_awaited()
    set_cookie = response.headers.get("set-cookie", "")
    assert override_settings.refresh_cookie_name in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


def test_logout_clears_cookie_when_revoke_fails(
    client: TestClient,
    override_settings: Settings,
) -> None:
    client.cookies.set(
        override_settings.refresh_cookie_name,
        "logout-refresh-token",
        path=override_settings.refresh_cookie_path,
    )

    with patch(
        "app.services.auth_service.logout",
        new=AsyncMock(side_effect=RuntimeError("db unavailable")),
    ):
        response = client.post("/auth/logout")

    assert response.status_code == 204
    set_cookie = response.headers.get("set-cookie", "")
    assert override_settings.refresh_cookie_name in set_cookie
    assert "Max-Age=0" in set_cookie or "max-age=0" in set_cookie.lower()


def test_consume_refresh_token_deletes_row() -> None:
    """consume_refresh_token must DELETE the row (not only SELECT it)."""
    token_hash = hash_refresh_token("plain-refresh")
    record = RefreshToken(
        id=uuid4(),
        user_id=uuid4(),
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    session.execute = AsyncMock(return_value=result)

    deleted = asyncio.run(consume_refresh_token(session, token_hash))

    assert deleted is record
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert isinstance(statement, Delete)
    session.flush.assert_awaited_once()


def test_delete_refresh_tokens_for_user_deletes_all_sessions() -> None:
    user_id = uuid4()
    session = AsyncMock()

    asyncio.run(delete_refresh_tokens_for_user(session, user_id))

    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert isinstance(statement, Delete)
    assert str(statement.whereclause) == "refresh_tokens.user_id = :user_id_1"


def test_me_without_bearer_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_with_valid_jwt(client: TestClient, override_settings: Settings) -> None:
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


def test_patch_me_updates_authenticated_users_full_name(
    client: TestClient, override_settings: Settings, db_session: AsyncMock
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    with patch("app.db.users.get_user_by_id", new=AsyncMock(return_value=user)):
        response = client.patch(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"full_name": "Updated Trainer"},
        )

    assert response.status_code == 200
    assert response.json()["email"] == user.email
    assert response.json()["full_name"] == "Updated Trainer"
    assert user.full_name == "Updated Trainer"
    db_session.commit.assert_awaited_once()


def test_patch_me_rejects_unexpected_profile_data(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    with patch("app.db.users.get_user_by_id", new=AsyncMock(return_value=user)):
        response = client.patch(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"email": "new@example.com", "full_name": "Trainer"},
        )

    assert response.status_code == 422


def test_change_password_updates_authenticated_user(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    get_user = AsyncMock(return_value=user)
    delete_user_tokens = AsyncMock()

    with (
        patch(
            "app.db.users.get_user_by_id",
            new=get_user,
        ),
        patch(
            "app.db.refresh_tokens.delete_refresh_tokens_for_user",
            new=delete_user_tokens,
        ),
    ):
        response = client.put(
            "/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "password123",
                "new_password": "new-password123",
            },
        )

    assert response.status_code == 204
    assert verify_password("new-password123", user.password_hash)
    assert not verify_password("password123", user.password_hash)
    get_user.assert_awaited_once_with(db_session, user.id)
    delete_user_tokens.assert_awaited_once_with(db_session, user.id)
    db_session.commit.assert_awaited_once()


def test_change_password_rejects_invalid_current_password(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)

    with patch(
        "app.db.users.get_user_by_id",
        new=AsyncMock(return_value=user),
    ):
        response = client.put(
            "/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "wrong-password",
                "new_password": "new-password123",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid current password"
    assert verify_password("password123", user.password_hash)
    db_session.commit.assert_not_awaited()


def test_change_password_rejects_user_id_in_payload(
    client: TestClient,
    override_settings: Settings,
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)

    with patch(
        "app.db.users.get_user_by_id",
        new=AsyncMock(return_value=user),
    ):
        response = client.put(
            "/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "password123",
                "new_password": "new-password123",
                "user_id": str(uuid4()),
            },
        )

    assert response.status_code == 422


def test_patch_me_rejects_a_blank_full_name(
    client: TestClient, override_settings: Settings
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    with patch("app.db.users.get_user_by_id", new=AsyncMock(return_value=user)):
        response = client.patch(
            "/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"full_name": "   "},
        )

    assert response.status_code == 422


def test_change_password_requires_a_valid_new_password_length(
    client: TestClient,
    override_settings: Settings,
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch(
        "app.db.users.get_user_by_id",
        new=AsyncMock(return_value=user),
    ):
        short_new_password = client.put(
            "/auth/me/password",
            headers=headers,
            json={"old_password": "password123", "new_password": "short"},
        )
        too_long_new_password = client.put(
            "/auth/me/password",
            headers=headers,
            json={"old_password": "password123", "new_password": "ą" * 37},
        )

    assert short_new_password.status_code == 422
    assert too_long_new_password.status_code == 422


def test_change_password_rejects_the_current_password_as_the_new_password(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    user = _local_user()
    access_token, _ = create_access_token(user.id, override_settings)
    delete_user_tokens = AsyncMock()

    with (
        patch(
            "app.db.users.get_user_by_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.db.refresh_tokens.delete_refresh_tokens_for_user",
            new=delete_user_tokens,
        ),
    ):
        response = client.put(
            "/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"old_password": "password123", "new_password": "password123"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "New password must differ from current password"
    assert verify_password("password123", user.password_hash)
    delete_user_tokens.assert_not_awaited()
    db_session.commit.assert_not_awaited()


def test_change_password_rejects_google_user(
    client: TestClient,
    override_settings: Settings,
    db_session: AsyncMock,
) -> None:
    user = User(
        id=uuid4(),
        email="google@example.com",
        full_name="Google Trainer",
        auth_method=AuthMethod.GOOGLE,
        oauth_subject="google-subject",
        password_hash=None,
    )
    access_token, _ = create_access_token(user.id, override_settings)

    with patch(
        "app.db.users.get_user_by_id",
        new=AsyncMock(return_value=user),
    ):
        response = client.put(
            "/auth/me/password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "old_password": "password123",
                "new_password": "new-password123",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Password change is unavailable for Google accounts"
    )
    db_session.commit.assert_not_awaited()


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
    assert "Path=/auth" in cookie_header
    assert "SameSite=lax" in cookie_header


def test_clear_refresh_cookie_attributes(test_settings: Settings) -> None:
    response = Response()
    clear_refresh_cookie(response, test_settings)
    cookie_header = response.headers.get("set-cookie", "")
    assert "refresh_token=" in cookie_header
    assert "Path=/auth" in cookie_header
    assert "Max-Age=0" in cookie_header or "max-age=0" in cookie_header.lower()


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
