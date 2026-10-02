> **Security upgrade:** Read the [setup and migration guide](security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

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
  docker compose -f src/docker-compose.yml up -d --build dashboard-backend data-eyes-mcp-dev
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
| `AI_PROVIDER` | `anthropic` | AI adapter: `anthropic`, `openai`/`chatgpt`, or `local` |
| `AI_ROUTINE_MODEL` | provider default | Model for short insights and background sweeps |
| `AI_DEEP_MODEL` | provider default | Model for Ask, Advisor, and detailed explanations |
| `AI_REQUEST_TIMEOUT_SECONDS` | `120` | Provider request timeout |
| `ANTHROPIC_API_KEY` | unset | Credential used when `AI_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | unset | Credential used when `AI_PROVIDER=openai` |
| `OPENAI_BASE_URL` | OpenAI API | OpenAI-compatible hosted API base URL |
| `LOCAL_AI_BASE_URL` | Ollama on Docker host | Local OpenAI-compatible API base URL |
| `LOCAL_AI_API_KEY` | unset | Optional credential for a protected local endpoint |

The bootstrap credentials are ignored after the first user is created. Manage
later users through the admin UI or API.

### AI provider examples

Only one provider is active at a time. Ask, Advisor, deep explanations, and
background insights all use the same adapter; the browser never receives an
API key.

Anthropic:

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=replace-me
AI_ROUTINE_MODEL=claude-haiku-4-5
AI_DEEP_MODEL=claude-opus-5
```

OpenAI API (the `chatgpt` alias is also accepted):

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=replace-me
AI_ROUTINE_MODEL=gpt-5-mini
AI_DEEP_MODEL=gpt-5
```

Local Ollama or another server exposing `/v1/chat/completions`:

```dotenv
AI_PROVIDER=local
LOCAL_AI_BASE_URL=http://host.docker.internal:11434/v1
AI_ROUTINE_MODEL=llama3.2
AI_DEEP_MODEL=llama3.2
```

Model names are configuration, not application logic. Set them to models that
exist in the selected account or local runtime, then rebuild/restart the
backend. The authenticated `/api/insights/status` endpoint reports the active
provider and model names without returning credentials.

## MCP environment

Create `src/mcp/.env` from `.env.example`.

| Variable | Default | Purpose |
|---|---:|---|
| `DEFAULT_INSTANCE` | first configured instance | Instance used when a tool omits `instance` |
| `DEFAULT_PRINCIPAL` | unset | Local/stdio authorization principal; HTTP should receive a proxy-injected principal |
| `DEPLOYMENT_ENVIRONMENT` | unset | Loads only instances in one environment |
| `INSTANCE_ALLOWLIST` | unset | Additional comma-separated instance boundary |
| `MSSQL_CONNECTION_TIMEOUT` | `30` | SQL connection timeout in seconds |
| `MSSQL_QUERY_TIMEOUT` | `30` | SQL execution timeout in seconds |
| `MAX_ROWS_PER_QUERY` | `50000` | Maximum returned rows |
| `MAX_QUERY_LENGTH` | `50000` | Maximum submitted SQL length |
| `MAX_RESPONSE_BYTES` | `2000000` | Hard cap on returned database content |
| `MAX_CELL_LENGTH` | `4000` | Hard cap on each textual value |
| `MAX_CONCURRENT_QUERIES` | `8` | Process-wide active-query ceiling |
| `READ_ONLY` | `true` | Enables SQL write-blocking policy |
| `ENABLE_WRITES` | `false` | Explicit write-mode switch; keep disabled for monitoring |
| `SECURITY_ENFORCEMENT` | `true` | Enables default-deny principal and object policy |
| `REQUIRE_SCOPED_CREDENTIALS` | `true` | Fails startup unless the deployment-specific SQL credentials exist |
| `ALLOW_REQUEST_CREDENTIALS` | `false` | Disables caller-provided SQL credentials |
| `DISABLE_ADHOC_ENVIRONMENTS` | `production,staging` | Environments where `execute_sql` is unavailable |
| `ALLOWED_HOST` | unset | Additional HTTP host allowed by DNS-rebinding protection |
| `LOG_LEVEL` | `INFO` | Application log level |
| `LOG_FORMAT` | `json` | `json` or `text` logs |
| `RATE_LIMIT_ENABLED` | `true` | Enables per-principal, per-process query limiting |
| `RATE_LIMIT_QUERIES_PER_MINUTE` | `60` | Maximum queries per principal per minute |
| `REPOSITORY_DSN` | Set by Compose | Lets MCP read dashboard trend history |

`MSSQL_CONNECTION_STRING` remains available as a single-instance fallback for
standalone MCP usage. In the unified stack, prefer `src/instances.yaml`.

## PostgreSQL password

Compose requires independent `DASHBOARD_REPO_PASSWORD` and `MCP_REPO_PASSWORD`; there is no insecure
fallback. Set both before first deployment, for example in the shell that starts
Compose:

```powershell
$env:DASHBOARD_REPO_PASSWORD = "replace-with-a-long-random-password"
$env:MCP_REPO_PASSWORD = "replace-with-an-independent-random-password"
docker compose -f src/docker-compose.yml up -d --build
```

Changing this value after PostgreSQL has initialized does not rewrite the
password stored in the existing volume. Coordinate credential rotation with a
database role-password change or recreate the development volume only when its
data is disposable.

## SQL Server permissions

Use one dedicated login per deployment, configured through each instance's
`credential_env_prefix`. Common monitoring queries require `VIEW SERVER STATE`;
schema exploration requires read access to target databases. Start from
`src/mcp/sql/provision-readonly-login.sql`, remove grants for tools you disabled,
and use encrypted SQL connections whenever the server supports them. See
[MCP security](mcp-security.md) for the complete authorization and isolation model.
