"""Shared repository quotas and bounded background password work."""

import app.infrastructure.postgres.pool as postgres_pool
import app.modules.auth.repository as auth_repository

import asyncio
import hashlib
from fastapi import HTTPException

_password_slots = asyncio.Semaphore(4)


async def password_work(fn, *args):
    try:
        await asyncio.wait_for(_password_slots.acquire(), timeout=1)
    except asyncio.TimeoutError:
        raise HTTPException(429, "Password service busy; try again shortly") from None
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    def done(task):
        _password_slots.release()
        if not task.cancelled():
            task.exception()
    task.add_done_callback(done)
    return await asyncio.shield(task)


async def quota(category: str, identity: str, limit: int, seconds: int):
    bucket = category + ":" + hashlib.sha256(identity.encode()).hexdigest()
    try:
        allowed = await auth_repository.consume_quota(bucket, limit, seconds)
    except postgres_pool.RepositoryUnavailable:
        raise HTTPException(503, "Security service unavailable") from None
    if not allowed:
        raise HTTPException(429, "Too many requests; try again later", headers={"Retry-After": str(seconds)})
