"""
User management API — admin-only except for changing your own password.

One shared team: any user can see/manage the same instance registry
(app/routers/instances.py); `role` only gates this router and nothing else.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import passwords, repository
from ..auth import require_admin, require_auth

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSummary(BaseModel):
    username: str
    role: str
    created_at: str


class CreateUserRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = "member"


class ChangePasswordRequest(BaseModel):
    password: str = Field(min_length=8)


@router.get("", response_model=list[UserSummary])
async def list_users(_: str = Depends(require_admin)):
    try:
        return await repository.list_users()
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"User registry unavailable: {e}") from e


@router.post("", response_model=UserSummary, status_code=201)
async def create_user(payload: CreateUserRequest, _: str = Depends(require_admin)):
    if payload.role not in ("admin", "member"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'member'")
    password_hash = passwords.hash_password(payload.password)
    try:
        user = await repository.create_user(payload.username, password_hash, role=payload.role)
    except repository.UsernameConflict as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"User registry unavailable: {e}") from e
    # create_user's return value has no created_at — list_users is the
    # source of truth for that; a freshly created row's timestamp is "now"
    # closely enough for the immediate response.
    return UserSummary(username=user["username"], role=user["role"], created_at=datetime.now(timezone.utc).isoformat())


@router.post("/me/password")
async def change_own_password(payload: ChangePasswordRequest, username: str = Depends(require_auth)):
    password_hash = passwords.hash_password(payload.password)
    try:
        await repository.update_user_password(username, password_hash)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"User registry unavailable: {e}") from e
    return {"ok": True}


@router.delete("/{username}", status_code=204)
async def delete_user(username: str, current_username: str = Depends(require_admin)):
    if username == current_username:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    try:
        deleted = await repository.delete_user(username)
    except repository.RepositoryUnavailable as e:
        raise HTTPException(status_code=503, detail=f"User registry unavailable: {e}") from e
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Unknown user: {username}")
