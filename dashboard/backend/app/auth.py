"""
Dashboard authentication — a single shared admin credential behind a signed
session cookie.

This is intentionally simple: one operator account, not a user database or
RBAC system. The rearchitecture plan's user decision was "basic login from
day one" specifically to avoid regressing on Grafana's built-in admin auth
(GF_SECURITY_ADMIN_USER/PASSWORD) — not to build a full identity system.
If multi-user access control is ever needed, replace this module; nothing
else in the backend assumes a single-user model beyond this file.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from .config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def require_auth(request: Request) -> str:
    """FastAPI dependency: raise 401 unless the session is authenticated."""
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return username


@router.post("/login")
def login(payload: LoginRequest, request: Request):
    # Constant-time comparisons — this gate gets probed more than most.
    valid_username = secrets.compare_digest(payload.username, settings.DASHBOARD_ADMIN_USERNAME)
    valid_password = secrets.compare_digest(payload.password, settings.DASHBOARD_ADMIN_PASSWORD)
    if not (valid_username and valid_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    request.session["username"] = payload.username
    return {"username": payload.username}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(username: str = Depends(require_auth)):
    return {"username": username}
