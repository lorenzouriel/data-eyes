-- Data Eyes dashboard

-- One row per (instance, category) per collection cycle. 
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

-- Instance registry: the database-backed fleet registry
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

-- User accounts: replaces the single shared DASHBOARD_ADMIN_USERNAME/PASSWORD credential. 
CREATE TABLE IF NOT EXISTS app_user (
    user_id        BIGSERIAL PRIMARY KEY,
    username       TEXT UNIQUE NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'member', -- 'admin' | 'member'
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Wait-category history: the design's Waits tab needs a real 24h
CREATE TABLE IF NOT EXISTS wait_category_snapshot (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name   TEXT NOT NULL,
    category        TEXT NOT NULL,
    seconds         DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_wait_category_snapshot_lookup
    ON wait_category_snapshot (instance_name, captured_at DESC);

-- Blocking-event log: the Blocking tab's "last 24 hours" list needs actual history
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

-- Activity sample log: append-only, one row per currently-active session per
-- collector cycle (diagnostics.active_sessions()).
CREATE TABLE IF NOT EXISTS activity_sample (
    sample_id         BIGSERIAL PRIMARY KEY,
    captured_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name     TEXT NOT NULL,
    session_id        INTEGER NOT NULL,
    database_name     TEXT,
    program_name      TEXT,
    host_name         TEXT,
    login_name        TEXT,
    wait_type         TEXT,
    wait_category     TEXT,
    wait_time_ms      DOUBLE PRECISION NOT NULL DEFAULT 0,
    elapsed_time_ms   DOUBLE PRECISION NOT NULL DEFAULT 0,
    plan_handle       TEXT,
    query_hash        TEXT,
    sql_text          TEXT
);

CREATE INDEX IF NOT EXISTS ix_activity_sample_lookup
    ON activity_sample (instance_name, captured_at DESC);

-- File IO history: delta-of-cumulative-counter, same technique as
-- wait_category_snapshot, against sys.dm_io_virtual_file_stats
CREATE TABLE IF NOT EXISTS file_io_snapshot (
    snapshot_id     BIGSERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name   TEXT NOT NULL,
    database_name   TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    drive           TEXT,
    io_stall_ms     DOUBLE PRECISION NOT NULL,
    io_bytes        DOUBLE PRECISION NOT NULL DEFAULT 0,
    io_count        DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_file_io_snapshot_lookup
    ON file_io_snapshot (instance_name, captured_at DESC);

-- Deadlock event log: durable copy of SQL Server's own system_health
-- Extended Events ring buffer, which has limited capacity and rolls over.
CREATE TABLE IF NOT EXISTS deadlock_event (
    event_id             BIGSERIAL PRIMARY KEY,
    occurred_at          TIMESTAMPTZ NOT NULL,
    captured_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    instance_name        TEXT NOT NULL,
    database_name        TEXT,
    victim_login         TEXT,
    victim_host          TEXT,
    victim_program       TEXT,
    resource_description TEXT,
    process_count        INTEGER NOT NULL,
    summary              TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_deadlock_event_dedup
    ON deadlock_event (instance_name, occurred_at);
CREATE INDEX IF NOT EXISTS ix_deadlock_event_lookup
    ON deadlock_event (instance_name, occurred_at DESC);

-- Advisor dismiss state: findings are generated fresh on every Advisor-tab
-- request (never cached server-side)
CREATE TABLE IF NOT EXISTS advisor_dismissal (
    instance_name  TEXT NOT NULL,
    finding_key    TEXT NOT NULL,
    dismissed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (instance_name, finding_key)
);
-- Idempotent startup migration for existing repositories; also in init.sql.
CREATE TABLE IF NOT EXISTS notification_channel (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('slack','teams','email','sms')),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notification_rule (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL REFERENCES notification_channel(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    definition JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS notification_state (
    instance_name TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (instance_name, category)
);
CREATE TABLE IF NOT EXISTS notification_log (
    id BIGSERIAL PRIMARY KEY,
    channel_id BIGINT REFERENCES notification_channel(id) ON DELETE SET NULL,
    rule_id BIGINT REFERENCES notification_rule(id) ON DELETE SET NULL,
    instance_name TEXT NOT NULL,
    category TEXT NOT NULL,
    event JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','sending','sent','failed','suppressed')),
    message TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS notification_log_due_idx ON notification_log(next_attempt_at)
    WHERE status IN ('pending','sending');
CREATE INDEX IF NOT EXISTS notification_log_rule_idx ON notification_log(rule_id, instance_name, created_at DESC);
