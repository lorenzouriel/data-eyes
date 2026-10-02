# MCP security model

HTTP requests require a deployment-specific bearer token. `HTTP_TOKEN_HASHES`
maps a configured principal to the SHA-256 hash of its random token. Identity
headers, including the old Base64 variant, are ignored. Only `/health` is public.
Stdio uses `DEFAULT_PRINCIPAL`. HTTP never falls back to that principal.

Authorization remains default-deny through `mcp_security.principals` in the shared
fleet file. SQL Server grants remain the final boundary. Keep tool, instance and
object grants explicit; use dedicated read-only SQL logins per environment.

`execute_sql` is disabled in every environment until a full T-SQL parser can
reliably authorize every referenced object and column. Use the fixed diagnostic
and discovery tools. No read-only/write-mode flag can enable ad-hoc SQL.

Compose binds direct MCP ports to loopback and supplies an HTTPS gateway.
Repository tools use a separate read-only PostgreSQL login and filter both by
principal grants and deployment scope. Changing token mappings requires restarting
the corresponding service; token revocation does not require changing SQL logins.

Query rate, concurrency, time, cell size and response limits remain enforced.
Database values are untrusted data, never instructions. Audit logs record security
decisions and SQL hashes without intentionally recording query contents.

See [Security hardening and upgrade guide](security-hardening.md) for full setup,
client token configuration, role provisioning, TLS, limitations and migration.
