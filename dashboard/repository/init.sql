-- Data Eyes dashboard — trend-history repository schema.
--
-- This database is dedicated to the dashboard's own history — it never
-- connects to a monitored SQL Server (that's what mcp/ is for). Matches
-- DPA's real architecture: performance history lives in its own repository,
-- separate from every system being watched, written by a persistent
-- collector process rather than a job running on the target (see
-- dashboard/backend/app/collector.py).
--
-- One row per (instance, category) per collection cycle. `category` values
-- match .claude/knowledge-base/_static/taxonomy.md's category names, plus
-- the synthetic "overall" category for the instance's overall_severity
-- (used by the Main Page fleet card trend strip).

CREATE TABLE IF NOT EXISTS metric_snapshot (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name   TEXT NOT NULL,
    overall_severity TEXT NOT NULL,
    category        TEXT NOT NULL,
    severity        TEXT NOT NULL,
    metric_value    DOUBLE PRECISION  -- nullable: not every category has a representative number (see dba_tools.py fleet_health_score's metric_specs)
);

-- The query this whole schema exists to serve: "give me this instance's
-- category over the last N hours, oldest first."
CREATE INDEX IF NOT EXISTS ix_metric_snapshot_lookup
    ON metric_snapshot (instance_name, category, captured_at DESC);

-- Retention is enforced by the collector (prune_old_snapshots in
-- dashboard/backend/app/repository.py), not by this schema — v1 keeps raw-
-- resolution rows up to a configurable window (TREND_RETENTION_DAYS) rather
-- than rolling fine-grained samples up into hourly/daily aggregates the way
-- DPA does. That tiered rollup is a reasonable follow-up if retention needs
-- to stretch far beyond what raw resolution can hold cheaply.

-- Instance registry — the database-backed fleet registry (replaces the old
-- instances.yaml-as-source-of-truth model). instances.yaml is now only a
-- one-time seed read at startup (see app/config.py's load_seed_instances(),
-- app/repository.py's seed_instances_from_yaml()); this table is what every
-- request actually reads/writes, managed through the dashboard UI
-- (app/routers/instances.py). connection_string_encrypted is Fernet-encrypted
-- (app/crypto.py) — this table NEVER holds a plaintext connection string.
CREATE TABLE IF NOT EXISTS instance (
    instance_id     BIGSERIAL PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    label           TEXT NOT NULL,
    environment     TEXT,
    connection_string_encrypted BYTEA NOT NULL,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- User accounts — replaces the single shared DASHBOARD_ADMIN_USERNAME/
-- PASSWORD credential. DASHBOARD_ADMIN_USERNAME/PASSWORD now only seed one
-- admin-role row here when this table is empty at startup (see
-- app/auth.py); every account after that is created through the UI by an
-- admin. password_hash is a bcrypt hash (app/passwords.py) — this table
-- NEVER holds a plaintext password. One shared team, not multi-tenant: every
-- user sees the same instance registry, there's no per-user data isolation.
CREATE TABLE IF NOT EXISTS app_user (
    user_id        BIGSERIAL PRIMARY KEY,
    username       TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'member', -- 'admin' | 'member'
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
