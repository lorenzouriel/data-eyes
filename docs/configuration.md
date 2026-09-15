# Configuration

Data Eyes separates fleet configuration from service behavior:

- `src/instances.yaml` defines the SQL Server fleet shared by the dashboard and
  MCP.
- `src/backend/.env` configures the dashboard backend.
- `src/mcp/.env` configures MCP policy, limits, logging, and local defaults.
- `DASHBOARD_REPO_PASSWORD` configures the Compose-managed PostgreSQL password.

Never commit real connection strings, passwords, encryption keys, or API keys.

## Shared instance file

Create the local file from the committed template:

```powershell
Copy-Item src/instances.example.yaml src/instances.yaml
```

The file has this shape:

```yaml
instances:
  - name: prod
    label: "Production SQL Server"
    environment: production
    mssql_connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=sql.example.internal,1433;Database=master;UID=data_eyes;PWD=replace-me;Encrypt=yes;TrustServerCertificate=no"
```

| Field | Required | Meaning |
|---|---:|---|
| `name` | Yes | Unique stable identifier used by URLs, MCP tool arguments, and history rows |
| `label` | Yes | Human-readable name shown in the dashboard and tool output |
| `environment` | No | Free-form classification such as `production`, `staging`, or `development` |
| `mssql_connection_string` | Yes | Complete `pyodbc` connection string for the monitored SQL Server |

Names must be unique. Both container images include Microsoft ODBC Drivers 17
and 18, so the driver named by the connection string must be one of those
installed versions.

### Ownership and synchronization

At backend startup, every YAML entry is encrypted and upserted into the
dashboard registry. For matching names, YAML values replace the stored values.
Dashboard-only entries are preserved, but MCP cannot see them because MCP reads
the YAML directly.

Use this rule:

- Put instances needed by both dashboard and agents in `src/instances.yaml`.
- Use dashboard-only entries only when the separation is intentional.
- Restart the backend and MCP after changing the YAML:

  ```powershell
  docker compose -f src/docker-compose.yml up -d --build dashboard-backend data-eyes-mcp
  ```

## Backend environment

Create `src/backend/.env` from `.env.example`. The required values are:

| Variable | Purpose |
|---|---|
| `DASHBOARD_ADMIN_USERNAME` | Username used only to seed the first admin account |
| `DASHBOARD_ADMIN_PASSWORD` | Password used only for the first admin seed |
| `SESSION_SECRET_KEY` | Signs dashboard session cookies |
| `INSTANCE_SECRET_KEY` | Fernet key used to encrypt SQL connection strings in PostgreSQL |

Generate secrets with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Other backend settings include:

| Variable | Default/example | Purpose |
|---|---|---|
| `INSTANCES_FILE` | `../instances.yaml` | Shared fleet path outside containers; Compose overrides it inside the container |
| `REPOSITORY_DSN` | Set by Compose | PostgreSQL connection; required by auth, registry, and history |
| `COLLECTOR_INTERVAL_SECONDS` | `60` | Fleet collection interval |
| `TREND_RETENTION_DAYS` | `30` | History retention window |
| `CORS_ALLOW_ORIGINS` | `[]` | Allowed browser origins for split local development |
| `ANTHROPIC_API_KEY` | unset | Enables optional Advisor, Ask, and explanation features |

The bootstrap credentials are ignored after the first user is created. Manage
later users through the admin UI or API.

## MCP environment

Create `src/mcp/.env` from `.env.example`.

| Variable | Default | Purpose |
|---|---:|---|
| `DEFAULT_INSTANCE` | first configured instance | Instance used when a tool omits `instance` |
| `MSSQL_CONNECTION_TIMEOUT` | `30` | SQL connection timeout in seconds |
| `MSSQL_QUERY_TIMEOUT` | `30` | SQL execution timeout in seconds |
| `MAX_ROWS_PER_QUERY` | `50000` | Maximum returned rows |
| `MAX_QUERY_LENGTH` | `50000` | Maximum submitted SQL length |
| `READ_ONLY` | `true` | Enables SQL write-blocking policy |
| `ENABLE_WRITES` | `false` | Explicit write-mode switch; keep disabled for monitoring |
| `ALLOWED_HOST` | unset | Additional HTTP host allowed by DNS-rebinding protection |
| `LOG_LEVEL` | `INFO` | Application log level |
| `LOG_FORMAT` | `json` | `json` or `text` logs |
| `RATE_LIMIT_ENABLED` | `false` | Enables per-process request limiting |
| `REPOSITORY_DSN` | Set by Compose | Lets MCP read dashboard trend history |

`MSSQL_CONNECTION_STRING` remains available as a single-instance fallback for
standalone MCP usage. In the unified stack, prefer `src/instances.yaml`.

## PostgreSQL password

Compose accepts `DASHBOARD_REPO_PASSWORD` and uses `change-me` only as a local
fallback. Set it before first deployment, for example in the shell that starts
Compose:

```powershell
$env:DASHBOARD_REPO_PASSWORD = "replace-with-a-long-random-password"
docker compose -f src/docker-compose.yml up -d --build
```

Changing this value after PostgreSQL has initialized does not rewrite the
password stored in the existing volume. Coordinate credential rotation with a
database role-password change or recreate the development volume only when its
data is disposable.

## SQL Server permissions

Use a dedicated login with the minimum access required by the diagnostics you
intend to run. Common monitoring queries require `VIEW SERVER STATE`; schema
exploration requires read access to target databases. Keep MCP in read-only
mode and use encrypted SQL connections whenever the server supports them.
