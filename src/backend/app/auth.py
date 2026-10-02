"""Dashboard authentication with revocable server-side sessions.

Members share fleet diagnostics. Only administrators may manage users and
instance connections. Cookies contain an opaque session ID, never cached roles.
"""

import logging
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import passwords, repository
from .config import settings
from .security_limits import password_work, quota

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A fixed decoy hash to verify against on "no such user" — normalizes login
# timing between "user doesn't exist" and "wrong password" so the endpoint
# doesn't leak which usernames are registered via response latency.
_DECOY_HASH = passwords.hash_password("decoy-password-never-matches")


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def require_auth(request: Request) -> str:
    token = request.session.get("sid")
    if not isinstance(token, str) or len(token) != 64:
        raise HTTPException(401, "Not authenticated")
    try:
        user = await repository.get_session_user(session_hash(token))
    except repository.RepositoryUnavailable:
        raise HTTPException(503, "Session service unavailable") from None
    if not user:
        request.session.clear()
        raise HTTPException(401, "Session expired or revoked")
    request.state.user = user
    return user["username"]


async def require_admin(request: Request, username: str = Depends(require_auth)) -> str:
    if request.state.user["role"] != "admin":
        raise HTTPException(403, "Admin role required")
    return username


@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    ip = (request.headers.get("x-real-ip") if settings.TRUST_X_REAL_IP else None) \
        or (request.client.host if request.client else "unknown")
    user_key = payload.username.casefold()
    await quota("login-global", "all", 120, 60)
    await quota("login-ip", ip, 30, 300)
    # Keyed by user+IP so one client's bad guesses can't lock the account out
    # for everyone; the looser per-user cap still bounds distributed guessing.
    await quota("login-user-ip", f"{user_key}|{ip}", 10, 300)
    await quota("login-user", user_key, 60, 300)
    try:
        user = await repository.get_user_by_username(payload.username)
        valid = await password_work(passwords.verify_password, payload.password,
                                    user["password_hash"] if user else _DECOY_HASH)
        if not user or not valid:
            raise HTTPException(401, "Invalid credentials")
        old_token = request.session.get("sid")
        if old_token:
            await repository.revoke_session(session_hash(old_token))
        token = secrets.token_hex(32)
        if not await repository.create_session(session_hash(token), user["username"],
                                               user["password_hash"], settings.SESSION_MAX_AGE_SECONDS):
            raise HTTPException(401, "Credentials changed; sign in again")
    except repository.RepositoryUnavailable:
        raise HTTPException(503, "User registry unavailable") from None
    request.session.clear()
    request.session["sid"] = token
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
async def logout(request: Request):
    token = request.session.get("sid")
    if token:
        try:
            await repository.revoke_session(session_hash(token))
        except repository.RepositoryUnavailable:
            raise HTTPException(503, "Session service unavailable; retry logout") from None
    request.session.clear()
    return {"ok": True}


@router.get("/me")
async def me(request: Request, username: str = Depends(require_auth)):
    return {"username": username, "role": request.state.user["role"]}


async def ensure_bootstrap_admin() -> bool:
    """Seed one admin-role account from DASHBOARD_ADMIN_USERNAME/PASSWORD if
    the user table is empty. Returns True if it created one. Called once at
    startup (see app/main.py's lifespan) — never touches an existing table,
    even if the env-var username differs from what's already there."""
    if await repository.count_users() > 0:
        return False
    password_hash = await password_work(passwords.hash_password, settings.DASHBOARD_ADMIN_PASSWORD)
    try:
        await repository.create_user(settings.DASHBOARD_ADMIN_USERNAME, password_hash, role="admin")
    except repository.UsernameConflict:
        return False
    return True
