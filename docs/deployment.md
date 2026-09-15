# Deployment

The supported integrated deployment uses
[`src/docker-compose.yml`](../src/docker-compose.yml). It builds the dashboard
frontend, dashboard backend, and MCP server locally, and runs PostgreSQL from
the official image.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2
- Network access from Docker containers to every monitored SQL Server
- SQL Server credentials with the required monitoring permissions
- Free host ports 8080, 8090, and 8091

## First startup

From the repository root:

```powershell
Copy-Item src/instances.example.yaml src/instances.yaml
Copy-Item src/backend/.env.example src/backend/.env
Copy-Item src/mcp/.env.example src/mcp/.env
```

Configure the copied files according to [Configuration](configuration.md), set
the PostgreSQL password, and start the stack:

```powershell
$env:DASHBOARD_REPO_PASSWORD = "replace-with-a-long-random-password"
docker compose -f src/docker-compose.yml up -d --build
```

If the terminal is already in `src/`, use:

```powershell
docker compose up -d --build
```

Do not use `-f src/docker-compose.yml` from inside `src`; that resolves to the
nonexistent path `src/src/docker-compose.yml`.

`--build` is intentional. The application images are local build targets, not
public images to pull from a registry.

## Services

| Compose service | Container | Host port | Dependency |
|---|---|---:|---|
| `dashboard-repo` | `data-eyes-dashboard-repo` | internal only | PostgreSQL volume and schema |
| `dashboard-backend` | `data-eyes-dashboard-backend` | 8090 | healthy repository |
| `dashboard-frontend` | `data-eyes-dashboard-frontend` | 8091 | backend |
| `data-eyes-mcp` | `data-eyes-mcp-server` | 8080 | healthy repository |

Both SQL-facing containers mount the same host file at
`/app/instances.yaml:ro`.

## Verify the deployment

Check container state:

```powershell
docker compose -f src/docker-compose.yml ps
```

Check application endpoints:

```powershell
curl.exe http://localhost:8090/api/health
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -I http://localhost:8091/
```

The backend and MCP containers should be healthy. MCP readiness can be
temporarily unavailable while connection checks complete; its response reports
status per configured instance without exposing credentials.

## Logs

Follow the whole stack:

```powershell
docker compose -f src/docker-compose.yml logs -f
```

Follow only the SQL-facing services:

```powershell
docker compose -f src/docker-compose.yml logs -f dashboard-backend data-eyes-mcp
```

## Configuration updates

After editing `src/instances.yaml` or either service `.env`, recreate the
affected services:

```powershell
docker compose -f src/docker-compose.yml up -d --build dashboard-backend data-eyes-mcp
```

The YAML is mounted read-only, but application configuration is loaded at
startup rather than watched continuously.

## Image updates

Rebuild application images and recreate services:

```powershell
docker compose -f src/docker-compose.yml build
docker compose -f src/docker-compose.yml up -d
```

Pull the PostgreSQL base image separately when an upgrade is intended:

```powershell
docker compose -f src/docker-compose.yml pull dashboard-repo
```

Review PostgreSQL release notes and take a backup before a major-version
upgrade; replacing the image tag alone is not a database upgrade procedure.

## Stop and remove containers

```powershell
docker compose -f src/docker-compose.yml down
```

This preserves the named PostgreSQL volume. `down -v` deletes repository data
and should only be used when the local users, registry, and history are
disposable.

## Common problems

### Compose cannot find the file

Match the command to the current directory:

- repository root: `docker compose -f src/docker-compose.yml ...`
- `src/`: `docker compose ...`

### Pull access denied for Data Eyes images

The backend, frontend, and MCP images are built locally. Add `--build` to the
startup command and inspect build errors if an image is missing.

### ODBC driver not found

Rebuild the current images. Both SQL-facing Dockerfiles install Drivers 17 and
18. Confirm inside a container with:

```powershell
docker compose -f src/docker-compose.yml exec dashboard-backend odbcinst -q -d
docker compose -f src/docker-compose.yml exec data-eyes-mcp odbcinst -q -d
```

### MCP readiness is unavailable

Read `/ready`, then verify DNS, firewall rules, SQL port, credentials, TLS
options, and the instance name shown as unavailable. A healthy `/health` with
an unavailable `/ready` means the process is running but a dependency check is
failing.

### A maintenance diagnostic reports missing `CommandLog`

`CommandLog` is created by Ola Hallengren's maintenance solution. Its absence
affects checks that depend on maintenance history; it does not mean the basic
SQL connection failed. See [SQL toolkits](sql-toolkits.md).
