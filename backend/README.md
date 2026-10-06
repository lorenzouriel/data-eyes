# Dashboard backend

FastAPI application for fleet monitoring, authentication, insights, and notifications.

- `app/main.py`: route and middleware assembly.
- `app/lifespan.py`: startup, schema initialization, and background workers.
- `app/core/`: settings, encryption, and shared limits.
- `app/infrastructure/`: PostgreSQL resources and the SQL Server client.
- `app/modules/`: feature-owned routes, behavior, and database queries.
- `tests/modules/`: feature regression tests.

From this directory, install with `uv sync --frozen --extra dev`, then run
`uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8090`.

Run tests with `uv run --extra dev pytest -q -o asyncio_mode=auto`.
Database integration tests require explicitly configured disposable databases.

See [configuration](../docs/getting-started/configuration.md) and
[development](../docs/development/development.md).
