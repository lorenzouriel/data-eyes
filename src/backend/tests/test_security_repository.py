"""Optional real-PostgreSQL checks against an explicitly supplied disposable DB."""
import asyncio
import os

import pytest
import pytest_asyncio

from app import repository
from app.config import settings


@pytest_asyncio.fixture
async def database(monkeypatch):
    dsn = os.environ.get("SECURITY_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set SECURITY_TEST_POSTGRES_DSN to a disposable test database")
    assert dsn.rsplit("/", 1)[-1] == "data_eyes_security_test", "Refusing a non-test database"
    monkeypatch.setattr(settings, "REPOSITORY_DSN", dsn)
    monkeypatch.setattr(repository, "_pool", None)
    pool = await repository.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS app_user (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL)")
    await repository.ensure_security_schema()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE app_user CASCADE; TRUNCATE security_rate_limit")
        await conn.execute("INSERT INTO app_user VALUES ('alice', 'old-hash', 'admin')")
    yield pool
    await repository.close_pool()


@pytest.mark.asyncio
async def test_session_expiry_password_revocation_and_deletion(database):
    assert await repository.create_session("token-one", "alice", "old-hash", 3600)
    assert await repository.create_session("token-two", "alice", "old-hash", 3600)
    assert (await repository.get_session_user("token-one"))["role"] == "admin"
    assert await repository.update_user_password("alice", "new-hash", "old-hash")
    assert await repository.get_session_user("token-one") is None
    assert await repository.get_session_user("token-two") is None
    assert not await repository.create_session("stale-login", "alice", "old-hash", 3600)
    assert await repository.create_session("fresh", "alice", "new-hash", 3600)
    async with database.acquire() as conn:
        await conn.execute("UPDATE app_user SET role='member' WHERE username='alice'")
    assert (await repository.get_session_user("fresh"))["role"] == "member"
    await repository.revoke_session("fresh")
    assert await repository.get_session_user("fresh") is None
    assert await repository.create_session("expired", "alice", "new-hash", -1)
    assert await repository.get_session_user("expired") is None
    assert await repository.create_session("deleted", "alice", "new-hash", 3600)
    await repository.delete_user("alice")
    assert await repository.get_session_user("deleted") is None
    async with database.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM app_session") == 0


@pytest.mark.asyncio
async def test_quota_is_atomic_across_connections_and_expires(database):
    outcomes = await asyncio.gather(*(repository.consume_quota("test", 5, 60) for _ in range(20)))
    assert sum(outcomes) == 5
    async with database.acquire() as conn:
        await conn.execute("UPDATE security_rate_limit SET expires_at=now()-interval '1 second'")
    assert await repository.consume_quota("test", 5, 60)


@pytest.mark.asyncio
async def test_password_change_and_concurrent_login_cannot_leave_stale_session(database):
    await asyncio.gather(repository.create_session("racing-login", "alice", "old-hash", 3600),
                         repository.update_user_password("alice", "new-hash", "old-hash"))
    assert await repository.get_session_user("racing-login") is None
