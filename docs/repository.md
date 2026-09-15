# PostgreSQL repository

The repository is Data Eyes' internal PostgreSQL database. It is application
infrastructure, not one of the monitored SQL Servers.

Schema source: [`src/repository/init.sql`](../src/repository/init.sql)

## Responsibilities

The repository stores:

- dashboard users, password hashes, and roles;
- the dashboard's encrypted SQL Server instance registry;
- periodic health and severity snapshots;
- wait-category history and resource-rate samples;
- blocking events;
- Advisor dismissal state.

The backend reads and writes these records. MCP receives a repository DSN so
its repository tools can read collected trends; live MCP SQL tools connect to
the monitored SQL Servers instead.

## Data ownership

| Data | Writer | Readers |
|---|---|---|
| Users and roles | Backend auth/admin APIs | Backend |
| Instance registry | YAML startup sync and dashboard admin API | Backend |
| Metric snapshots | Backend collector | Backend and MCP repository tools |
| Wait snapshots | Backend collector | Backend and MCP repository tools |
| Blocking events | Backend collector | Backend |
| Advisor dismissals | Backend Advisor API | Backend |

## Connection-string protection

SQL Server connection strings are encrypted before entering PostgreSQL using
the backend's `INSTANCE_SECRET_KEY`. The YAML file itself contains the original
value and must be protected as a secret-bearing deployment file.

Losing `INSTANCE_SECRET_KEY` makes existing encrypted registry values
undecryptable. Rotating it therefore requires decrypting and re-encrypting the
stored values or rebuilding the registry from the shared YAML.

## Initialization and persistence

Compose runs `init.sql` when the PostgreSQL data volume is created. The named
volume `dashboard-repo-data` persists across container recreation and image
updates.

Initialization scripts do not rerun against an existing volume. Schema changes
after first deployment need an explicit migration; editing `init.sql` alone
only affects new volumes.

## Retention

The backend collector prunes time-series data according to
`TREND_RETENTION_DAYS`. This controls operational history growth but is not a
backup policy. Back up the PostgreSQL volume separately if users, trends, or
dashboard-only registry entries must survive host loss.

## Security

- Do not expose port 5432 publicly; the Compose service is internal-only by
  default.
- Replace the development PostgreSQL password before first deployment.
- Restrict the MCP repository account to read-only permissions in hardened
  deployments.
- Back up both the repository and the instance encryption key using separate,
  protected storage.
