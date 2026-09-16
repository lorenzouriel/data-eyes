# MCP security model

Data Eyes uses defense in depth. MCP authorization reduces accidental exposure;
SQL Server permissions remain the final security boundary. MCP authentication is
not implemented yet, so HTTP deployments must sit behind a trusted proxy that
removes caller-provided `X-Data-Eyes-Principal` headers and injects a verified
principal. Local/stdio deployments use `DEFAULT_PRINCIPAL`.

## Default-deny authorization

`src/instances.yaml` contains `mcp_security.principals`. Every principal needs
explicit tool and instance grants. Object-bearing tools additionally require a
matching database, schema, table, and column grant. Patterns use shell-style
matching; an empty list grants nothing. Keep production grants explicit instead
of using `*`.

```yaml
mcp_security:
  principals:
    reporting-agent:
      tools: [list_tables, describe_table, execute_sql]
      instances: [dev]
      objects:
        - databases: [Sales]
          schemas: [reporting]
          tables: [daily_summary, customer_totals]
          columns: [business_date, region, total]
```

`execute_sql` is disabled by default for `production` and `staging`. Where it is
enabled, it accepts one read-only SELECT, rejects external data access and
`SELECT INTO`, requires directly named columns, and authorizes every referenced
table. Complex analysis should be implemented as a fixed reviewed tool or view.

## Deployment isolation and credentials

The main Compose stack runs development MCP on port 8080. Staging and production
are separate profile-gated services on ports 8081 and 8082:

```powershell
docker compose -f src/docker-compose.yml --profile staging up -d data-eyes-mcp-staging
docker compose -f src/docker-compose.yml --profile production up -d data-eyes-mcp-prod
```

Each service filters the shared fleet file by environment and instance. Each
instance declares a `credential_env_prefix`; for example, `PROD` consumes
`PROD_MSSQL_USER` and `PROD_MSSQL_PASSWORD`. `REQUIRE_SCOPED_CREDENTIALS=true`
prevents fallback to broad credentials embedded for the dashboard. Provision a
separate login using `src/mcp/sql/provision-readonly-login.sql`, reviewing its
server and schema grants first.

Copy the matching credential template (`.env.dev.example`,
`.env.staging.example`, or `.env.production.example`) to the filename without
`.example`. Compose mounts only that credential file into its matching MCP
service and blanks the other environments' credential variables.

The committed policy grants only the `master` database as a safe starting
point. Add each application database, schema, table, and column explicitly to
the relevant principal after the matching SQL Server grants have been applied.

## Resource and output controls

The server enforces hard maximums. Clients may request smaller values but cannot
raise them:

- `MSSQL_QUERY_TIMEOUT`
- `MAX_ROWS_PER_QUERY`
- `MAX_RESPONSE_BYTES`
- `MAX_CELL_LENGTH`
- `MAX_CONCURRENT_QUERIES`
- `RATE_LIMIT_QUERIES_PER_MINUTE`

ODBC statement timeouts are set on the cursor. On application timeout Data Eyes
also calls `cursor.cancel()`. SQL Server Resource Governor remains recommended
for production because only the database can reliably bound scans, memory grants,
and CPU after a client disconnects.

## Untrusted database content and auditing

Structured output carries `_meta.trust=untrusted_database_content`; table and CSV
output contain the equivalent warning. Long cells and total result bytes are
truncated. This reduces prompt-injection exposure but cannot make stored text
trusted—the consuming agent must never treat returned values as instructions.

Structured security audit events record principal, tool, instance, database,
decision/reason, duration, returned rows, and response bytes. Query text is not
logged.
