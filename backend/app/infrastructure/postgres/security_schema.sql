CREATE TABLE IF NOT EXISTS app_session (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES app_user(username) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_app_session_user ON app_session(username);
CREATE INDEX IF NOT EXISTS ix_app_session_expiry ON app_session(expires_at);
CREATE TABLE IF NOT EXISTS security_rate_limit (
    bucket TEXT PRIMARY KEY,
    attempts INTEGER NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_security_rate_expiry ON security_rate_limit(expires_at);
