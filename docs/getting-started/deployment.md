> **Security upgrade:** Read the [setup and migration guide](../security/security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Deployment

The supported integrated deployment uses
[`docker-compose.yml`](../../docker-compose.yml). It builds the dashboard
frontend, dashboard backend, and MCP server locally, and runs PostgreSQL from
the official image.

## Prerequisites

- Docker Desktop or Docker Engine with Compose v2
- Network access from Docker containers to every monitored SQL Server
- SQL Server credentials with the required monitoring permissions
- Free host ports 8080 (loopback MCP) and 8443 (HTTPS gateway)

## First startup

From the repository root:

```powershell
Copy-Item .env.example .env
   Copy-Item instances.example.yaml instances.yaml
Copy-Item backend/.env.example backend/.env
Copy-Item mcp/.env.example mcp/.env
```

Configure the copied files according to [Configuration](configuration.md), set
the PostgreSQL password, and start the stack:

```powershell
$env:DASHBOARD_REPO_PASSWORD = "replace-with-a-long-random-password"
docker compose -f docker-compose.yml up -d --build
```

Run Compose commands from the repository root. `docker-compose.yml` retains
the historical project name `src` so the existing `src_dashboard-repo-data`,
`src_gateway-data`, and `src_gateway-config` volumes remain attached after the
folder move. If a deployment previously used `-p` or `COMPOSE_PROJECT_NAME`,
continue using that same project name.

`--build` is intentional. The application images are local build targets, not
public images to pull from a registry.

## Services

| Compose service | Container | Host port | Dependency |
|---|---|---:|---|
| `dashboard-repo` | `data-eyes-dashboard-repo` | internal only | PostgreSQL volume and schema |
| `dashboard-backend` | `data-eyes-dashboard-backend` | internal only | healthy repository |
| `dashboard-frontend` | `data-eyes-dashboard-frontend` | internal only | backend |
| `data-eyes-mcp` | `data-eyes-mcp-server` | 8080 | healthy repository |

Both SQL-facing containers mount the same host file at
`/app/instances.yaml:ro`.

## Verify the deployment

Check container state:

```powershell
docker compose -f docker-compose.yml ps
```

Check application endpoints:

```powershell
curl.exe https://localhost:8443/api/health
curl.exe http://localhost:8080/health
curl.exe http://localhost:8080/ready
curl.exe -I https://localhost:8443/
```

The backend and MCP containers should be healthy. MCP readiness can be
temporarily unavailable while connection checks complete; its response reports
status per configured instance without exposing credentials.

## Logs

Follow the whole stack:

```powershell
docker compose -f docker-compose.yml logs -f
```

Follow only the SQL-facing services:

```powershell
docker compose -f docker-compose.yml logs -f dashboard-backend data-eyes-mcp
```

## Configuration updates

After editing `instances.yaml` or either service `.env`, recreate the
affected services:

```powershell
docker compose -f docker-compose.yml up -d --build dashboard-backend data-eyes-mcp
```

The YAML is mounted read-only, but application configuration is loaded at
startup rather than watched continuously.

## Image updates

Rebuild application images and recreate services:

```powershell
docker compose -f docker-compose.yml build
docker compose -f docker-compose.yml up -d
```

Pull the PostgreSQL base image separately when an upgrade is intended:

```powershell
docker compose -f docker-compose.yml pull dashboard-repo
```

Review PostgreSQL release notes and take a backup before a major-version
upgrade; replacing the image tag alone is not a database upgrade procedure.

## Stop and remove containers

```powershell
docker compose -f docker-compose.yml down
```

This preserves the named PostgreSQL volume. `down -v` deletes repository data
and should only be used when the local users, registry, and history are
disposable.

## Common problems

### Compose cannot find the file

Match the command to the current directory:

- repository root: `docker compose -f docker-compose.yml ...`
- `src/`: `docker compose ...`

### Pull access denied for Data Eyes images

The backend, frontend, and MCP images are built locally. Add `--build` to the
startup command and inspect build errors if an image is missing.

### ODBC driver not found

Rebuild the current images. Both SQL-facing Dockerfiles install Drivers 17 and
18. Confirm inside a container with:

```powershell
docker compose -f docker-compose.yml exec dashboard-backend odbcinst -q -d
docker compose -f docker-compose.yml exec data-eyes-mcp odbcinst -q -d
```

### MCP readiness is unavailable

Read `/ready`, then verify DNS, firewall rules, SQL port, credentials, TLS
options, and the instance name shown as unavailable. A healthy `/health` with
an unavailable `/ready` means the process is running but a dependency check is
failing.

### A maintenance diagnostic reports missing `CommandLog`

`CommandLog` is created by Ola Hallengren's maintenance solution. Its absence
affects checks that depend on maintenance history; it does not mean the basic
SQL connection failed. See [SQL toolkits](../integrations/sql-toolkits.md).
