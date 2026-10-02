# Security hardening and upgrade guide

This change addresses the eight findings in the September 2026 review and the
additional deployment, AI, and access-control improvements. It changes defaults
and requires configuration before restarting an existing deployment. It does not
rotate your existing credentials or modify your private `instances.yaml`.

## What changes, and why

| Area | Before | Now | Benefit / tradeoff |
|---|---|---|---|
| MCP HTTP authentication | Caller identity headers and a default principal | Random bearer tokens verified against deployment-local SHA-256 hashes; identity headers ignored | Knowing a principal name or sending the Base64 variant cannot impersonate it. Clients need a token. |
| MCP transport | Publicly bound HTTP ports | Loopback-only MCP ports, authenticated HTTP, stateless requests, HTTPS gateway | Removes unauthenticated remote access and shared protocol-session identity ambiguity. Remote clients use TLS. |
| Ad-hoc SQL | Regex authorization could miss UNION columns and comma-join tables | `execute_sql` always denies; fixed diagnostic/discovery tools remain | Closes the bypass without pretending a regex is a SQL parser. Free-form querying is unavailable pending a fully reviewed parser. |
| Dashboard sessions | Signed cookies containing username/role | Opaque random session ID; only its hash is stored in PostgreSQL; every request checks the current user and absolute expiry | Logout, deletion, and password changes revoke access. Role checks use current database state. Repository failure denies access. |
| Password changes | Any valid cookie could change a password | Current password required, atomic compare/update, all user sessions deleted | A stolen cookie alone cannot change credentials. Everyone signs in again after a password change. |
| Session transport | HTTP and non-Secure cookies | HTTPS gateway; Secure, HttpOnly, SameSite=Strict cookies | Prevents sending dashboard cookies over ordinary HTTP. The local CA must be trusted. |
| Login | Unlimited attempts and blocking bcrypt on the event loop | Shared PostgreSQL account/IP/global quotas; at most four password jobs per worker | Reduces guessing and password-hashing denial of service. Busy callers receive 429. |
| SQL resources | Async timeout could leave work running | ODBC connection statement timeout, cursor cancellation, bounded concurrency, bounded result data | Limits pressure on monitored servers. Capacity stays reserved until a worker actually exits. |
| SQL TLS examples | Driver 17, optional encryption, trusted server certificate | Driver 18, explicit encryption, certificate validation | Reduces interception risk. SQL Server certificates must be trusted and match the hostname. |
| Repository discovery | Whole registry returned | Both deployment and principal filtering, including explicit trend targets | Development callers cannot enumerate out-of-scope production instances. |
| Instance administration | Any authenticated member could edit/test connections | Admin-only changes/tests; exact operator-controlled server allowlist and restricted ODBC options | Members cannot redirect backend connections. Adding a new server requires updating the allowlist. |
| Repository credentials | Shared writer account, fallback password | Required independent passwords; MCP gets SELECT on a metadata view and snapshots only | MCP cannot read user/session/connection-secret tables or modify application data with its assigned login. |
| AI data | Raw diagnostic text could leave the service | Captured SQL/plans/credentials omitted; other free text redacted; numeric metrics and severity retained | Reduces disclosure of SQL literals and sensitive diagnostic content. Advice has less detail; SQL/DDL-specific advice may be unavailable. |
| AI resources | Unbounded history and repeated generation | Per-user/global quotas, bounded history/context, concurrency and wall-clock deadlines | Limits accidental costs and abusive requests. Excess requests fail clearly. |
| Build/CI | Python images resolved dependencies at build time; apps ran as root | Frozen lockfiles, non-root application containers, minimal build contexts, dependency and secret scanning | More reproducible builds and smaller blast radius. Vulnerabilities still need ongoing patching. |

User-entered AI questions and chat history are still intentionally sent to the
configured provider. Do not paste secrets into those inputs. Numeric metrics and
severity are still diagnostic data; choose a local provider when required by your
data-handling rules. The application never executes AI-proposed DDL.

## Required upgrade steps

Back up the repository first. These instructions apply configuration; the code
review itself does not restart your running stack.

1. Copy `src/.env.example` to `src/.env`. Set independent, random values for
   `DASHBOARD_REPO_PASSWORD` and `MCP_REPO_PASSWORD`. A 32-byte random hex string
   is suitable and avoids URL-escaping issues in the DSNs. For an existing
   PostgreSQL volume, `DASHBOARD_REPO_PASSWORD` must initially match the database's
   actual password: changing an environment variable does not rotate it.

2. Configure each HTTP MCP deployment in its own `.env.dev`, `.env.staging`, or
   `.env.production`. Generate a different token for every principal/deployment.
   This example prints a token and its configuration; run it locally and store
   the token in your client secret store:

   ```powershell
   python -c "import secrets,hashlib,json; t=secrets.token_urlsafe(32); print('Client token:',t); print('HTTP_TOKEN_HASHES='+json.dumps({'development-agent':hashlib.sha256(t.encode()).hexdigest()}))"
   ```

   Put only the JSON mapping after `HTTP_TOKEN_HASHES=` in the appropriate
   deployment env file. Replace `development-agent` with the corresponding
   configured principal. Tokens map to existing `mcp_security.principals` grants.
   Never reuse a token across principals. Remove old `PRINCIPAL_HEADER` settings.
   `DEFAULT_PRINCIPAL` is only for local stdio clients; it cannot authenticate HTTP.

   HTTP requests must include `Authorization: Bearer <token>`. Both normal and
   Base64 principal headers are ignored. All HTTP endpoints except `/health`
   require a token, including `/ready`, `/metrics`, and `/info`. Tokens have no
   automatic expiry: rotate/revoke them by replacing/removing hashes and
   restarting that MCP deployment. This is static bearer authentication, not an
   OAuth authorization server or interactive sign-in flow.

3. Set a random `SESSION_SECRET_KEY` of at least 32 characters, the bootstrap
   password (12–72 characters, at most 72 UTF-8 bytes), and the existing
   `INSTANCE_SECRET_KEY` in `src/backend/.env`. Do not replace the encryption key
   without migrating encrypted connection strings. Leave `SESSION_HTTPS_ONLY=true`.
   Existing signed username/role cookies will require a fresh login.

4. Set `SQL_ALLOWED_SERVERS` to a JSON array of the exact ODBC Server values admins
   may add/edit/test, e.g. `["sql.internal,1433"]`. New connection strings must use
   Driver 18, `Encrypt=yes`, `TrustServerCertificate=no`, and a dedicated SQL login.
   Only the documented driver/server/database/login/TLS/application-intent options
   are accepted. Duplicate keys and dangerous ODBC trace/file/driver options are
   rejected. This is a name allowlist, not DNS pinning: use trusted DNS and network
   egress controls. Previously saved/YAML connections are not silently rewritten;
   update their TLS options and credentials after installing trusted certificates.

5. Provision the read-only MCP repository role. Fresh databases do this through
   `20-mcp-reader.sh`. For an existing volume, recreate only the repository service
   to supply its new environment/mount (without deleting the volume), then run:

   ```powershell
   docker compose -f src/docker-compose.yml up -d dashboard-repo
   docker compose -f src/docker-compose.yml exec -T dashboard-repo sh /docker-entrypoint-initdb.d/20-mcp-reader.sh
   ```

   The script creates/updates `data_eyes_mcp`, a metadata-only view, and narrowly
   scoped SELECT grants. It also removes PUBLIC CREATE on the `public` schema of
   this dedicated repository. Do not run it on an unrelated shared database.
   Standalone MCP deployments must use this read-only account in `REPOSITORY_DSN`
   or omit the DSN to disable repository tools.

6. Rebuild/start the application after configuring its files:

   ```powershell
   docker compose -f src/docker-compose.yml up -d --build
   ```

   Backend startup automatically applies the idempotent `app/security_schema.sql`
   migration to create session and quota tables. It deliberately refuses startup
   if that migration fails. No destructive migration or password reset is performed.

7. Open **https://localhost:8443**. The old dashboard/frontend and backend host
   ports 8091/8090 are no longer published. The gateway uses a persistent internal
   CA. Copy its **public root certificate** and install it in the appropriate
   client trust store after verifying it:

   ```powershell
   docker compose -f src/docker-compose.yml cp gateway:/data/caddy/pki/authorities/local/root.crt ./data-eyes-local-ca.crt
   ```

   Do not export/share the CA private key or disable certificate verification.
   The gateway runs as an unprivileged user, so it cannot install trust on the host
   automatically. See [Caddy's local HTTPS documentation](https://caddyserver.com/docs/automatic-https#local-https).
   For LAN access explicitly set `DASHBOARD_BIND_IP` and `DASHBOARD_HOST`, distribute
   the CA to clients, and set `ALLOWED_HOST` to that DNS name in MCP env files.
   For public deployments replace `tls internal` with your managed certificate/ACME
   configuration and firewall the internal services; this bundle does not provision
   public DNS or public certificates.

   Gateway MCP URLs are `/mcp` (development), `/staging/mcp`, and `/production/mcp`.
   The latter two require their existing Compose profiles. Loopback ports
   8080/8081/8082 remain available to local trusted clients. Do not expose them
   directly to a network; remote clients should use the HTTPS gateway.

For direct local frontend/backend development, `SESSION_HTTPS_ONLY=false` is an
explicit development-only escape hatch. Bind development servers to loopback.
Do not use this setting for network-accessible deployments.

## Limits and operations

- Login: 120 attempts/minute globally, 30 attempts/5 minutes/IP, and 10 attempts/
  5 minutes/normalized username. Password change: five attempts/5 minutes/user.
  Quotas live in PostgreSQL and are shared across backend workers. Behind the
  bundled proxy, IP limits may conservatively share a proxy address; account and
  global limits still apply. Do not trust arbitrary forwarded-IP headers.
- Sessions: absolute `SESSION_MAX_AGE_SECONDS` expiry (default 12 hours). Reissuing
  a cookie never extends the database expiry. Logout deletes that session; changing
  a password deletes all sessions; deleting an account cascades session deletion.
- SQL: `SQL_MAX_CONCURRENT_QUERIES=8` per backend worker, 30-second statement limit,
  10-second connection ceiling, one-second capacity wait, 50,000-row ceiling,
  2 MB cell-data budget, 100,000-character cell ceiling. The serialized HTTP envelope
  adds overhead. Oversized cells/results are truncated and marked internally.
  Very large individual driver values may allocate memory before truncation;
  database-side resource limits are still useful.
- AI: 30 generation requests/hour/user, 300 provider calls/hour globally (including
  background sweeps), `AI_MAX_CONCURRENT_REQUESTS=2` per worker, provider deadline
  `AI_REQUEST_TIMEOUT_SECONDS` (default 120 seconds), up to 20 chat messages, 4,000
  characters/message, 12,000 history characters, 16,000 diagnostic context characters,
  and 32,000 total provider-input characters. Gateway/frontend request bodies are
  limited to 128 KB. Requests rejected by quotas can count against other quotas.
- Sessions and quotas require PostgreSQL availability. Expired records are pruned
  during new sessions/quota use. Use standard database backup/access monitoring.
- Preserve least-privilege SQL Server logins; application checks are an additional
  boundary, not a substitute for database permissions. Administrators remain trusted
  operators, and dashboard members can still see the shared fleet's diagnostics.

## Validation

Frontend dependencies were upgraded to patched Vite 7 and React Router 7 releases.
Both Python lockfiles are audited; the older MCP transitive dependencies were
refreshed within the declared constraints.

Regression tests cover bearer authentication/header forgery, ad-hoc denial,
repository visibility, revoked-cookie replay, current-role checks, password
reauthentication, throttling, destination/ODBC validation, cancellation capacity,
and AI limits/redaction. Optional PostgreSQL tests exercise actual transaction
semantics, session deletion/expiry, concurrent login/password changes and atomic
quotas against a disposable database named `data_eyes_security_test`.

The security workflow audits locked Python dependencies, frontend dependencies,
and repository secrets. It never requires production credentials. Configure the
Gitleaks license secret if your GitHub organization requires one for that action.


### Recorded verification for this change

- MCP: 25 passing tests, including authenticated requests through the actual MCP HTTP transport.
- Backend: 17 passing tests, including three tests against disposable PostgreSQL 16.
- Actual repository reader privileges: metadata/snapshots readable; user table,
  encrypted connection table and snapshot INSERT denied.
- Frontend TypeScript/Vite production build passed after dependency upgrades.
- Backend, MCP and frontend Docker builds passed; installed backend/MCP packages
  import as non-root users outside the source directory; Nginx configuration passed.
- Gateway Caddy configuration and Compose configuration validated.
- Frontend npm audit and both locked Python dependency audits reported no known
  vulnerabilities at verification time. This is not a guarantee against new advisories.
- Lint and Git whitespace checks passed. Live SQL Server execution and production
  certificate trust were not exercised. No application deployment was performed.
