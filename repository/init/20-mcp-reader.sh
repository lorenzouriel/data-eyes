#!/bin/sh
set -eu
: "${MCP_REPO_PASSWORD:?Set a unique MCP_REPO_PASSWORD}"
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 --set=reader_password="$MCP_REPO_PASSWORD" <<'SQL'
SELECT 'CREATE ROLE data_eyes_mcp LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'data_eyes_mcp')\gexec
ALTER ROLE data_eyes_mcp PASSWORD :'reader_password';
ALTER ROLE data_eyes_mcp SET default_transaction_read_only = on;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE data_eyes_dashboard TO data_eyes_mcp;
GRANT USAGE ON SCHEMA public TO data_eyes_mcp;
CREATE OR REPLACE VIEW mcp_instance_summary AS SELECT name, label, environment FROM instance;
GRANT SELECT ON mcp_instance_summary, metric_snapshot TO data_eyes_mcp;
SQL
