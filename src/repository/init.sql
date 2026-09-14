-- Data Eyes dashboard — trend-history repository schema.
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

CREATE INDEX IF NOT EXISTS ix_metric_snapshot_lookup
    ON metric_snapshot (instance_name, category, captured_at DESC);

-- Instance registry — the database-backed fleet registry (replaces the old
-- instances.yaml-as-source-of-truth model).
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
-- admin-role row here when this table is empty at startup
CREATE TABLE IF NOT EXISTS app_user (
    user_id        BIGSERIAL PRIMARY KEY,
    username       TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'member', -- 'admin' | 'member'
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wait-category history — the design's Waits tab needs a real 24h
-- stacked-by-category chart, not just a live snapshot.
CREATE TABLE IF NOT EXISTS wait_category_snapshot (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name   TEXT NOT NULL,
    category        TEXT NOT NULL,
    seconds         DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_wait_category_snapshot_lookup
    ON wait_category_snapshot (instance_name, captured_at DESC);

-- Blocking-event log — the Blocking tab's "last 24 hours" list needs actual
-- history, not a re-labeled live snapshot. 
CREATE TABLE IF NOT EXISTS blocking_event (
    event_id          BIGSERIAL PRIMARY KEY,
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name     TEXT NOT NULL,
    root_sql          TEXT,
    lock_type         TEXT,
    blocked_count     INTEGER NOT NULL,
    duration_seconds  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_blocking_event_lookup
    ON blocking_event (instance_name, captured_at DESC);

-- Advisor dismiss state — findings are generated fresh on every Advisor-tab
-- request (never cached server-side), so this table holds only the one bit
-- that must survive across requests: "the DBA already saw and dismissed
-- this one." 
CREATE TABLE IF NOT EXISTS advisor_dismissal (
    instance_name  TEXT NOT NULL,
    finding_key    TEXT NOT NULL,
    dismissed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (instance_name, finding_key)
);
