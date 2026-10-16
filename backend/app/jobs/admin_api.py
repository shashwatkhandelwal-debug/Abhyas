"""Admin demo control: POST /admin/fast-forward/{teacher_id} (spec/07 §7.4, spec/08 §8.6).

Mounted by the coordinator in main.py (`app.include_router(jobs_admin_router)`).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.auth.csrf import verify_csrf_token
from backend.app.auth.guards import require_role
from backend.app.db.models import AppUser
from backend.app.jobs.tick import fast_forward_teacher

router = APIRouter(prefix="/admin", tags=["Admin"])


class JobOutcomeOut(BaseModel):
    job_id: uuid.UUID
    kind: str
    status: str
    error: str | None = None


class FastForwardOut(BaseModel):
    teacher_id: uuid.UUID
    advanced: int
    processed: list[JobOutcomeOut]


@router.post(
    "/fast-forward/{teacher_id}",
    response_model=FastForwardOut,
    dependencies=[Depends(verify_csrf_token)],
)
async def fast_forward(
    teacher_id: uuid.UUID,
    _admin: Annotated[AppUser, Depends(require_role("admin"))],
) -> FastForwardOut:
    """Runs a teacher's pending scheduled jobs now (demo control; admin only)."""
    result = await fast_forward_teacher(teacher_id)
    return FastForwardOut(
        teacher_id=teacher_id,
        advanced=result.advanced,
        processed=[
            JobOutcomeOut(job_id=o.job_id, kind=o.kind, status=o.status, error=o.error)
            for o in result.outcomes
        ],
    )
