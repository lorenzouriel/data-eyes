-- Idempotent startup migration for the alert catalog (app/modules/alerts).
-- instance_name '' is the fleet-wide default; a named instance overrides it.
CREATE TABLE IF NOT EXISTS alert_setting (
    alert_setting_id   BIGSERIAL PRIMARY KEY,
    alert_key          TEXT NOT NULL,
    instance_name      TEXT NOT NULL DEFAULT '',
    enabled            BOOLEAN,
    warning_threshold  DOUBLE PRECISION,
    critical_threshold DOUBLE PRECISION,
    tier               TEXT CHECK (tier IN ('fast','standard','slow','daily')),
    confirm_samples    INTEGER CHECK (confirm_samples BETWEEN 1 AND 10),
    excluded_databases TEXT[],
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alert_key, instance_name)
);

-- Latest evaluation per instance and alert. severity is the confirmed value
-- written to metric_snapshot; observed_severity/streak back the
-- "confirm after N samples" double check.
CREATE TABLE IF NOT EXISTS alert_state (
    instance_name     TEXT NOT NULL,
    alert_key         TEXT NOT NULL,
    severity          TEXT NOT NULL,
    observed_severity TEXT NOT NULL,
    streak            INTEGER NOT NULL DEFAULT 1,
    metric_value      DOUBLE PRECISION,
    detail            TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','error')),
    status_message    TEXT NOT NULL DEFAULT '',
    checked_at        TIMESTAMPTZ NOT NULL,
    changed_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (instance_name, alert_key)
);

-- Event alerts (deadlocks, failed jobs, restarts...) never clear, so each
-- occurrence is stored once and dispatched once.
CREATE TABLE IF NOT EXISTS alert_event (
    alert_event_id BIGSERIAL PRIMARY KEY,
    instance_name  TEXT NOT NULL,
    alert_key      TEXT NOT NULL,
    dedup_key      TEXT NOT NULL,
    severity       TEXT NOT NULL CHECK (severity IN ('WARNING','CRITICAL')),
    occurred_at    TIMESTAMPTZ NOT NULL,
    captured_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_value   DOUBLE PRECISION,
    detail         TEXT NOT NULL DEFAULT '',
    dispatched     BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (instance_name, alert_key, dedup_key)
);
CREATE INDEX IF NOT EXISTS nix_alert_event_pending ON alert_event (alert_event_id) WHERE NOT dispatched;
CREATE INDEX IF NOT EXISTS nix_alert_event_captured_at ON alert_event (captured_at DESC);

-- Watermarks and baselines that event and delta checks carry between cycles.
CREATE TABLE IF NOT EXISTS alert_memory (
    instance_name TEXT NOT NULL,
    alert_key     TEXT NOT NULL,
    memory        JSONB NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (instance_name, alert_key)
);

-- Daily DB checklist: one fleet-wide summary sent to the selected channels.
CREATE TABLE IF NOT EXISTS alert_digest_setting (
    alert_digest_setting_id INTEGER PRIMARY KEY CHECK (alert_digest_setting_id = 1),
    enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    hour_utc     INTEGER NOT NULL DEFAULT 7 CHECK (hour_utc BETWEEN 0 AND 23),
    channel_ids  BIGINT[] NOT NULL DEFAULT '{}',
    last_sent_on DATE
);
INSERT INTO alert_digest_setting (alert_digest_setting_id) VALUES (1) ON CONFLICT DO NOTHING;
