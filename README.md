# Backend TaePlanDo

## Local setup

1. Copy `.env.example` to `.env` and adjust the values if needed.
2. Start PostgreSQL:

   ```powershell
   docker compose up -d
   ```

3. Install dependencies and apply the schema:

   ```powershell
   py -m uv sync --group dev
   py -m uv run alembic upgrade head
   ```

4. Start the API:

   ```powershell
   py -m uv run uvicorn app.main:app --reload
   ```

   The health endpoint is available at `http://127.0.0.1:8000/health`.

If port `5432` is already used, set the same free port in both `POSTGRES_PORT`
and `DATABASE_URL` (for example `5433`).

## Auth API (short)

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/auth/register` | Create LOCAL trainer → access JWT + HttpOnly refresh cookie (auto-login) |
| `POST` | `/auth/login` | Email/password → access JWT + HttpOnly refresh cookie |
| `POST` | `/auth/refresh` | Cookie → new access JWT + rotated refresh cookie |
| `POST` | `/auth/logout` | Revokes refresh token server-side and clears the cookie (`204`) |
| `GET` | `/auth/me` | Bearer access JWT → current user |
| `GET` | `/auth/google` | Start Google OAuth |
| `GET` | `/auth/google/callback` | OAuth callback → refresh cookie + redirect to SPA |

Duplicate email on register returns `409` with `{"detail":"Email already registered"}`.
Refresh cookie path defaults to `/api/auth` (Vite proxy) so both refresh and logout receive it.
After logout, `/auth/refresh` fails and `/auth/me` still requires a valid (unexpired) access JWT.

## Training groups API (short)

All endpoints below require `Authorization: Bearer <access-token>` and operate
only on groups owned by that trainer.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/training-groups?duration_minutes=60&min_age=7&max_age=14` | List and optionally filter the trainer's groups, including `plan_ids`. |
| `POST` | `/training-groups` | Create a group from `name`, `min_age`, `max_age`, and `duration_minutes`; its starting schema is 100% `MAIN`. |
| `GET` | `/training-groups/{group_id}` | Return one owned group, including its `plan_ids`. |
| `PUT` | `/training-groups/{group_id}` | Replace all editable group fields; the body never accepts `id` or `trainer_id`. |
| `DELETE` | `/training-groups/{group_id}` | Delete a group together with its plans and plan exercises. |
| `DELETE` | `/training-groups/trainer/{trainer_id}` | Delete all groups of the OAuth-authenticated trainer only. |

Example creation payload:

```json
{
  "name": "Młodzież początkująca",
  "min_age": 7,
  "max_age": 14,
  "duration_minutes": 60
}
```

## Quality checks

```powershell
py -m uv run ruff check .
py -m uv run mypy src
py -m uv run pytest
```
