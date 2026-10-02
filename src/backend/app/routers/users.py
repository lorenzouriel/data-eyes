"""
User management API — admin-only except for changing your own password.

One shared fleet: members can read diagnostics; admins manage users and instances.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .. import passwords, repository
from ..auth import require_admin, require_auth
from ..security_limits import password_work, quota

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSummary(BaseModel):
    username: str
    role: str
    created_at: str


def _fits_bcrypt(value: str) -> str:
    if len(value.encode()) > 72:
        raise ValueError("Password must be at most 72 UTF-8 bytes")
    return value


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=72)
    role: str = "member"

    _check_password = field_validator("password")(_fits_bcrypt)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=12, max_length=72)

    _check_password = field_validator("password")(_fits_bcrypt)


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
    password_hash = await password_work(passwords.hash_password, payload.password)
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
async def change_own_password(payload: ChangePasswordRequest, request: Request, username: str = Depends(require_auth)):
    await quota("password-change", username, 5, 300)
    expected_hash = request.state.user["password_hash"]
    if not await password_work(passwords.verify_password, payload.current_password, expected_hash):
        raise HTTPException(403, "Current password is incorrect")
    password_hash = await password_work(passwords.hash_password, payload.password)
    try:
        if not await repository.update_user_password(username, password_hash, expected_hash):
            raise HTTPException(409, "Credentials changed; sign in again")
    except repository.RepositoryUnavailable:
        raise HTTPException(503, "User registry unavailable") from None
    request.session.clear()
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
