"""Route guards and authentication dependencies (spec/09 §9.7)."""

import uuid
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.session import SESSION_COOKIE_NAME, verify_session_token
from backend.app.config import settings
from backend.app.db.models import AppUser
from backend.app.db.session import get_db_session


async def get_current_user_optional(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AppUser | None:
    """Returns authenticated AppUser if valid session cookie exists.

    Authorization: Bearer header is permitted ONLY in non-production environments (test suites).
    """
    token: str | None = request.cookies.get(SESSION_COOKIE_NAME)

    # Allow Authorization: Bearer token ONLY when ENVIRONMENT != "production" (test suites)
    if not token and settings.ENVIRONMENT != "production":
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if not token:
        return None

    payload = verify_session_token(token)
    if not payload:
        return None

    user_id_raw = payload.get("user_id")
    if not user_id_raw:
        return None

    try:
        user_uuid = uuid.UUID(str(user_id_raw))
    except ValueError:
        return None

    stmt = select(AppUser).where(AppUser.id == user_uuid)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    return user


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> AppUser:
    """Enforces authentication, raising HTTP 401 if not logged in."""
    user = await get_current_user_optional(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*allowed_roles: str) -> Callable[..., Any]:
    """Dependency factory checking that current user has one of allowed roles or is admin (§9.7)."""

    async def role_checker(
        current_user: Annotated[AppUser, Depends(get_current_user)],
    ) -> AppUser:
        # Admin can view all pages (§9.7)
        if current_user.role == "admin" or current_user.role in allowed_roles:
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role required: {', '.join(allowed_roles)}",
        )

    return role_checker
