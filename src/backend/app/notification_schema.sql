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
