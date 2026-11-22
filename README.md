# Backend TaePlanDo

## Prerequisites

Install and start both of the following before setting up the project:

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) with Docker
  Compose available. Verify it with `docker compose version`.
- The `uv` [CLI](https://docs.astral.sh/uv/getting-started/installation/). Verify
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

The seed is idempotent. It keeps one local demo trainer and creates the four
fixed segments, 24 global training types, 14 global equipment types, 318 global
exercises, eight exercise histories with two approved versions, three training
groups, and five historical plans per group. The current demo credentials are
defined in `src/app/db/seed.py`.

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

| Method  | Path                    | Notes                                                                                                      |
| ------- | ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `POST`  | `/auth/register`        | Create LOCAL trainer → access JWT + HttpOnly refresh cookie (auto-login)                                   |
| `POST`  | `/auth/login`           | Email/password → access JWT + HttpOnly refresh cookie                                                      |
| `POST`  | `/auth/refresh`         | Cookie → new access JWT + rotated refresh cookie                                                           |
| `POST`  | `/auth/logout`          | Revokes refresh token server-side and clears the cookie (`204`)                                            |
| `GET`   | `/auth/me`              | Bearer access JWT → current user                                                                           |
| `PATCH` | `/auth/me`              | Bearer access JWT + `{ "full_name" }` → updated current user                                               |
| `PUT`   | `/auth/me/password`     | Bearer access JWT + `old_password`, `new_password` → password changed and refresh sessions revoked (`204`) |
| `GET`   | `/auth/google`          | Start Google OAuth                                                                                         |
| `GET`   | `/auth/google/callback` | OAuth callback → refresh cookie + redirect to SPA                                                          |

Duplicate email on register returns `409` with `{"detail":"Email already registered"}`.
Local passwords on register / password change must be at least 8 characters and include a
letter, a digit, and a special character.
Refresh cookie path defaults to `/api/auth` (Vite proxy) so both refresh and logout receive it.
After logout, `/auth/refresh` fails and `/auth/me` still requires a valid (unexpired) access JWT.

## Equipment API (short)

All endpoints below require `Authorization: Bearer <access-token>`. A trainer sees
global equipment types and types they created themselves.

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/equipment?page=1&page_size=20` | Return one page of equipment types visible to the trainer. |
| `POST` | `/equipment` | Create a trainer-owned local equipment type from `{ "name" }`. |

## Training segments API (short)

All endpoints below require `Authorization: Bearer <access-token>`. Segments are
a fixed system catalog (seeded; not trainer-owned CRUD).

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/training-segments` | Return all training segments (`id`, `code`, `name`) for schema editing. |

## Training groups API (short)

All endpoints below require `Authorization: Bearer <access-token>` and operate
only on groups owned by that trainer.

| Method   | Path                                                                            | Notes                                                                                                         |
| -------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `GET`    | `/training-groups?duration_minutes=60&min_age=7&max_age=14&page=1&page_size=20` | List one page of the trainer's groups, including `plan_ids` and `schema`; ages default to `0`–`99`.           |
| `POST`   | `/training-groups`                                                              | Create a group from `name`, `min_age`, `max_age`, and `duration_minutes`; its starting schema is 100% `MAIN`. |
| `GET`    | `/training-groups/{group_id}`                                                   | Return one owned group, including its `plan_ids` and `schema`.                                                |
| `PUT`    | `/training-groups/{group_id}`                                                   | Replace all editable group fields; the body never accepts `id` or `trainer_id`.                               |
| `PUT`    | `/training-groups/{group_id}/schema`                                            | Replace the group's full training schema (ordered parts); see payload below.                                  |
| `DELETE` | `/training-groups/{group_id}`                                                   | Delete a group together with its plans and plan exercises.                                                    |
| `DELETE` | `/training-groups/trainer`                                                      | Delete all groups of the OAuth-authenticated trainer.                                                         |

Schema replace rules: each `segment_id` at most once, percentages sum to `100`,
each percentage in `(0, 100]`, array order becomes `position` `1..n`, and every
`segment_id` must exist in `/training-segments`. Unknown group → `404`; invalid
schema → `422`.

Example list response:

```json
{
  "items": [
    {
      "id": "bcac9a67-d89d-468e-b253-735854bf9494",
      "trainer_id": "22a97e32-f84e-41e0-aa89-59f0576d8ba0",
      "name": "Test",
      "min_age": 7,
      "max_age": 14,
      "duration_minutes": 60,
      "created_at": "2026-10-13T13:28:17.727677Z",
      "updated_at": "2026-10-13T13:28:17.727677Z",
      "plan_ids": [],
      "schema": [
        {
          "segment_id": 3,
          "segment_code": "MAIN",
          "segment_name": "Ćwiczenia",
          "percentage": "100.00",
          "position": 1
        }
      ]
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

Example creation payload:

```json
{
  "name": "Test",
  "min_age": 7,
  "max_age": 14,
  "duration_minutes": 60
}
```

Example schema replace payload (`PUT /training-groups/{group_id}/schema`):

```json
{
  "items": [
    { "segment_id": 1, "percentage": 20 },
    { "segment_id": 3, "percentage": 70 },
    { "segment_id": 4, "percentage": 10 }
  ]
}
```

## Quality checks

```powershell
uv run ruff check .
uv run mypy src
uv run pytest
```

## Exercise media (SCRUM-284)

`seed-exercise-media` imports the SCRUM-282 artist package into S3-compatible
storage (including Cloudflare R2). Configure the `EXERCISE_MEDIA_*` variables
from `.env.example`; credentials stay outside Git. The application itself does
not require storage credentials at startup. Apply migrations and seed the
catalogue before importing.

The checked-in `src/app/media/exercise_media.csv` maps all 318 catalogue source
IDs to the delivered folders and SHA-256 checksums. Each exercise has light/dark
WebP thumbnails, SVG thumbnails and animated WebP files. Source `0` is the
standalone SVG placeholder; it does not create an exercise in the database.
Binary assets are supplied separately and are not committed to this repository.

```powershell
uv run alembic upgrade head
# For a database without the catalogue:
uv run seed-system-data

# Use the final directory containing 1-bieg-miedzy-liniami, etc.
uv run seed-exercise-media import --media-root "C:/path/to/final" --dry-run
uv run seed-exercise-media import --media-root "C:/path/to/final"
```

The preflight checks every local file and the seeded exercise/version identities
before uploading. The dry run does not require storage credentials. Objects use
stable keys `exercises/<source_id>/<filename>`.
A repeated import skips unchanged SHA-256 metadata and overwrites missing or
changed objects at the same keys, with the correct content type and a one-hour
public cache lifetime. Storage permission errors are failures, not missing files.
URLs are committed in one database transaction after all uploads succeed. On a
failure, rerun the same command; uploaded objects are reusable. Existing object
keys may already have been replaced before a failed import completes.

The exercise API accepts and returns:

| Field | Asset |
| --- | --- |
| `image_url` | Dark thumbnail (existing compatible field) |
| `animation_url` | Dark animation |
| `image_url_light` | Light thumbnail |
| `animation_url_light` | Light animation |

Fields are nullable for exercises without media. A private-exercise update from
an older client preserves omitted new media fields; an explicit `null` clears
one. Global exercise list responses resolve media from the approved version.
The importer updates the catalogue exercise and its deterministic approved seed
versions, including archived seed versions still used by trainer configurations.
It leaves custom moderation versions and historical plan snapshots unchanged.
Ordinary catalogue seeding preserves imported media URLs on existing rows.
SVG variants are uploaded too, under the manifest's stable keys. Displaying media
and theme selection in the frontend belong to SCRUM-285.

For a deliberately revised artist delivery, regenerate and review the manifest
before importing. The builder requires the complete catalogue and exact file set:

```powershell
uv run seed-exercise-media build-manifest --media-root "C:/path/to/final"
```

Automated coverage uses S3 request stubs and checks manifest mapping/checksums,
repeat uploads, replacements, permission failures, transactional DB linkage,
light/dark API payloads, legacy edits and explicit clearing. CI applies migrations
and verifies their round trip using PostgreSQL.
