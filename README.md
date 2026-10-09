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

## Quality checks

```powershell
py -m uv run ruff check .
py -m uv run mypy src
py -m uv run pytest
```
