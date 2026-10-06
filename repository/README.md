# PostgreSQL repository

This folder contains the database initialization assets for Data Eyes.

- `init/10-init.sql` creates the application tables on a new PostgreSQL volume.
- `init/20-mcp-reader.sh` provisions the restricted MCP reader role.

Root `docker-compose.yml` mounts both scripts into PostgreSQL's initialization
directory. Initialization runs only for an empty data volume.

Existing databases receive the current security and notification schema updates
through `backend/app/infrastructure/postgres/schema.py` during backend startup.
The SQL files remain packaged with that Python module so installed applications
and container images can load them. Keep their definitions synchronized with
`init/10-init.sql`.

Application database queries belong to each backend feature's `repository.py`.
Connection pooling belongs to `backend/app/infrastructure/postgres/pool.py`.
MCP history queries live in `mcp/src/data_eyes_mcp/tools/history.py`.

See [database architecture](../docs/architecture/repository.md) and
[deployment](../docs/getting-started/deployment.md).
