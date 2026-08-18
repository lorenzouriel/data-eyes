"""
Dashboard authentication — real user accounts (app_user table) behind a
signed session cookie.

Bootstrap: DASHBOARD_ADMIN_USERNAME/PASSWORD only matter once, to create the
first admin account when app_user is empty (see ensure_bootstrap_admin(),
called from app/main.py's lifespan) — a day-one login path without a
chicken-and-egg registration step. After that they're unused; accounts are
created through the UI by an admin (see app/routers/users.py).

One shared team, not multi-tenant: every logged-in user sees and manages the
same instance registry (app/routers/instances.py) — there's no per-user data
isolation. `role` only gates user management itself (see require_admin).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from . import passwords, repository
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# A fixed decoy hash to verify against on "no such user" — normalizes login
# timing between "user doesn't exist" and "wrong password" so the endpoint
# doesn't leak which usernames are registered via response latency.
_DECOY_HASH = passwords.hash_password("decoy-password-never-matches")


class LoginRequest(BaseModel):
    username: str
    password: str


def require_auth(request: Request) -> str:
    """FastAPI dependency: raise 401 unless the session is authenticated."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return username


def require_admin(request: Request) -> str:
    """FastAPI dependency: raise 401/403 unless the session belongs to an admin."""
    username = require_auth(request)
    if request.session.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return username


@router.post("/login")
async def login(payload: LoginRequest, request: Request):
    try:
        user = await repository.get_user_by_username(payload.username)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"User registry unavailable: {e}") from e
    if not user:
        passwords.verify_password(payload.password, _DECOY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not passwords.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    request.session["username"] = user["username"]
    request.session["role"] = user["role"]
    return {"username": user["username"], "role": user["role"]}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request, username: str = Depends(require_auth)):
    return {"username": username, "role": request.session.get("role", "member")}


async def ensure_bootstrap_admin() -> bool:
    """Seed one admin-role account from DASHBOARD_ADMIN_USERNAME/PASSWORD if
    the user table is empty. Returns True if it created one. Called once at
    startup (see app/main.py's lifespan) — never touches an existing table,
    even if the env-var username differs from what's already there."""
    if await repository.count_users() > 0:
        return False
    password_hash = passwords.hash_password(settings.DASHBOARD_ADMIN_PASSWORD)
    try:
        await repository.create_user(settings.DASHBOARD_ADMIN_USERNAME, password_hash, role="admin")
    except repository.UsernameConflict:
        return False
    return True
