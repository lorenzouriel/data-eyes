"""
Backend liveness — distinct from SQL Server fleet health (that's
GET /api/fleet). Unauthenticated: container orchestrators and Docker
healthchecks need to reach this without a session cookie.
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"status": "ok"}
