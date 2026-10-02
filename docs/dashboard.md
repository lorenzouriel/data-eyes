> **Security upgrade:** Read the [setup and migration guide](security-hardening.md) before starting this version. HTTP MCP requires bearer tokens; ad-hoc SQL is disabled; the dashboard uses HTTPS on port 8443.

# Dashboard

The dashboard is the human-facing interface to Data Eyes. It consists of a
React frontend and a FastAPI backend. The backend connects directly to SQL
Server, evaluates health, and persists history in the Data Eyes PostgreSQL
repository.

## Frontend

Source: [`src/frontend/`](../src/frontend/)

The frontend uses React, TypeScript, React Router, and Vite. The fleet index is
kept separate from each instance's scrollable dashboard:

| Page | Responsibility |
|---|---|
| Login | Authenticates against the backend session API |
| Fleet index | Displays and filters configured instances, then opens the selected instance |
| Instance dashboard | One continuous page for Resources, Waits, Blocking, Sessions, SQL, and Advisor |
| Ask | Runs optional multi-turn fleet analysis |
| Account | Changes the current user's password |
| Admin | Manages users and dashboard registry entries |

The production Docker image builds static assets and serves them through
Nginx. During development, Vite runs on port `5173` and the backend CORS setting
must allow that origin.

## Backend

Source: [`src/backend/`](../src/backend/)

The backend uses FastAPI, `pyodbc`, `asyncpg`, Pydantic settings, signed session
cookies, bcrypt password hashes, and Fernet encryption for stored connection
strings.

Major modules:

| Module | Responsibility |
|---|---|
| `app/main.py` | Application lifecycle, middleware, routers, startup synchronization |
| `app/config.py` | Environment and shared-YAML loading |
| `app/mssql_client.py` | Bounded SQL Server query execution |
| `app/diagnostics.py` | Fixed monitoring queries and structured diagnostic results |
| `app/health_score.py` | Severity evaluation and fleet/category rollups |
| `app/repository.py` | PostgreSQL access for users, registry, trends, and events |
| `app/collector.py` | Periodic health and trend collection |
| `app/auth.py` | Login, logout, sessions, and authorization dependencies |
| `app/ai_provider.py` | Provider adapters for Anthropic, OpenAI, and local models |
| `app/insights_agent.py` | Provider-neutral prompts, explanations, and fleet questions |
| `app/insights_sweep.py` | Optional background insights generation |

## API areas

| Prefix | Purpose |
|---|---|
| `/api/health` | Backend liveness |
| `/api/auth` | Login, logout, and current-user identity |
| `/api/users` | User administration and password changes |
| `/api/instances` | Registry CRUD and instance detail data |
| `/api/fleet` | Fleet-wide evaluated health |
| `/api/instances/{name}/tabs` | Per-instance diagnostic tabs |
| `/api/instances/{name}/trend` | Historical category severity |
| `/api/insights` | Feed, streams, Advisor, Explain, and Ask |

Interactive API documentation is available from FastAPI at
`http://127.0.0.1:8090/docs` when running the backend locally for development.
Compose does not publish the backend port.

## Health model

Diagnostics return structured values and severities rather than treating every
metric as a generic chart. Category severity rolls up to instance severity,
and instance severity rolls up to fleet status using the worst active level.
The frontend renders both the current evaluation and historical trend data.

Some checks depend on optional SQL Server features or operational tables. For
example, maintenance-history checks use Ola Hallengren's `CommandLog`. If that
table is absent, the specific diagnostic may be unavailable even though the
SQL connection and the rest of the dashboard are healthy.

## Authentication and roles

The first startup seeds one administrator when the user table is empty. After
that, user accounts are stored in PostgreSQL and managed through the Admin page
or API. The supported roles are:

- `admin`: user and instance-registry administration plus normal dashboard use
- `member`: normal authenticated dashboard use

Sessions use an opaque ID in a signed Secure/HttpOnly/SameSite=Strict cookie.
PostgreSQL validates each session and current role. Logout revokes that session;
password changes revoke all sessions and require the current password.
Use a strong `SESSION_SECRET_KEY`, and
terminate TLS at a trusted reverse proxy in deployed environments.

## Instance registry behavior

The backend queries the encrypted PostgreSQL registry at runtime. On startup,
it synchronizes every shared-YAML entry into that registry. This enables the
dashboard UI to retain dashboard-only entries while ensuring that YAML-managed
entries stay aligned with MCP. See [Configuration](configuration.md).

## Background collection

The collector periodically queries registered instances and writes trend data
to PostgreSQL. Collection failures are isolated per instance so one unavailable
server does not stop the fleet loop. Retention pruning uses
`TREND_RETENTION_DAYS`.

## Optional insights

Advisor, Ask, explanations, and the background insight sweep use the provider
selected by `AI_PROVIDER`. Anthropic and OpenAI require their matching API key;
local mode targets an OpenAI-compatible endpoint such as Ollama. If the
selected provider is not configured, monitoring, authentication, registry, and
history continue normally. Ask and Advisor show a configuration message rather
than an empty generated result.


### Fleet severity interpretation

Fleet health uses Critical > Warning > Unknown > OK. A failed diagnostic is
Unknown, and Unknown instances have their own filter rather than being counted
as Healthy.

Accumulated wait percentages describe the distribution of waits, not current
utilization or distress. They remain available for analysis but do not generate
Warning/Critical alerts. Internal SOS_WORK_DISPATCHER waits are excluded.
Blocking and other operational diagnostics retain their alert thresholds.

Backup history is local to each monitored SQL Server. For an availability-group
database, missing or stale local history is Unknown because a different replica
may have performed the backup. This check does not yet consolidate histories
across replicas; verify them before concluding a backup was missed. Standalone
backup thresholds remain enforced. Unknown CHECKDB history also remains visible.
