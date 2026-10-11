# Backend TaePlanDo

## Prerequisites
Install and start both of the following before setting up the project:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker
  Compose available. Verify it with `docker compose version`.
- The [`uv` CLI](https://docs.astral.sh/uv/getting-started/installation/). Verify
  it with `uv --version`. It manages the project's Python 3.12+ runtime and
  dependencies.

## Local setup

1. Copy `.env.example` to `.env` and adjust the values if needed. Keep
   `POSTGRES_PORT` and the port in `DATABASE_URL` in sync.
2. Start PostgreSQL:

   ```powershell
   docker compose up -d --wait
   ```

3. Install dependencies and apply the schema:

   ```powershell
   uv sync --group dev
   uv run alembic upgrade head
   ```

4. Seed the system dictionaries and local demo data:

   ```powershell
   uv run seed-system-data
   ```

   The seed is idempotent. It creates or updates the local demo data; the
   current demo credentials are defined in `src/app/db/seed.py`.

5. Start the API:

   ```powershell
   uv run uvicorn app.main:app --reload
   ```

   The health endpoint is available at `http://127.0.0.1:8000/health`.

If port `5432` is already used, set the same free port in both `POSTGRES_PORT`
and `DATABASE_URL` (for example `5433`).

## Database reset and verification

To recreate the local database from scratch, run the following commands from the
repository root. The first command permanently removes this project's local
PostgreSQL volume.

```powershell
docker compose down --volumes
docker compose up -d --wait
uv run alembic upgrade head
uv run seed-system-data
```

Verify that the schema and seed data were restored:

```powershell
docker compose exec -T postgres psql -U taeplando -d taeplando -c "SELECT email, full_name FROM users ORDER BY email;"
docker compose exec -T postgres psql -U taeplando -d taeplando -c "SELECT id, code, name FROM training_segments ORDER BY id;"
```

The first query should return the seeded local users, and the second should return
four fixed training segments.
## Auth API (short)

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/auth/register` | Create LOCAL trainer → access JWT + HttpOnly refresh cookie (auto-login) |
| `POST` | `/auth/login` | Email/password → access JWT + HttpOnly refresh cookie |
| `POST` | `/auth/refresh` | Cookie → new access JWT + rotated refresh cookie |
| `POST` | `/auth/logout` | Revokes refresh token server-side and clears the cookie (`204`) |
| `GET` | `/auth/me` | Bearer access JWT → current user |
| `PATCH` | `/auth/me` | Bearer access JWT + `{ "full_name" }` → updated current user |
| `PUT` | `/auth/me/password` | Bearer access JWT + `old_password`, `new_password` → password changed and refresh sessions revoked (`204`) |
| `GET` | `/auth/google` | Start Google OAuth |
| `GET` | `/auth/google/callback` | OAuth callback → refresh cookie + redirect to SPA |

Duplicate email on register returns `409` with `{"detail":"Email already registered"}`.
Local passwords on register / password change must be at least 8 characters and include a
letter, a digit, and a special character. Login only enforces minimum length (8).
Refresh cookie path defaults to `/api/auth` (Vite proxy) so both refresh and logout receive it.
After logout, `/auth/refresh` fails and `/auth/me` still requires a valid (unexpired) access JWT.

## Training groups API (short)

All endpoints below require `Authorization: Bearer <access-token>` and operate
only on groups owned by that trainer.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/training-groups?duration_minutes=60&min_age=7&max_age=14&page=1&page_size=20` | List one page of the trainer's groups, including `plan_ids`; ages default to `0`–`99`. |
| `POST` | `/training-groups` | Create a group from `name`, `min_age`, `max_age`, and `duration_minutes`; its starting schema is 100% `MAIN`. |
| `GET` | `/training-groups/{group_id}` | Return one owned group, including its `plan_ids`. |
| `PUT` | `/training-groups/{group_id}` | Replace all editable group fields; the body never accepts `id` or `trainer_id`. |
| `DELETE` | `/training-groups/{group_id}` | Delete a group together with its plans and plan exercises. |
| `DELETE` | `/training-groups/trainer` | Delete all groups of the OAuth-authenticated trainer. |

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
uv run ruff check .
uv run mypy src
uv run pytest
```
