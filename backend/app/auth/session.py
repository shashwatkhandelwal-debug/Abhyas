"""Session management using signed HttpOnly cookies (spec/09 §9.7).

Follows spec requirements:
- Cookie name: 'abhyas_session'
- Signed via itsdangerous using settings.SESSION_SECRET
- Expiration: 12 hours (43200 seconds)
- HttpOnly, SameSite=Lax, Secure in production
"""

from typing import Any

from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.app.config import settings

SESSION_COOKIE_NAME = "abhyas_session"
SESSION_MAX_AGE_SECONDS = 12 * 3600  # 12 hours (§9.7)
SESSION_SALT = "abhyas-session-salt"


def get_serializer() -> URLSafeTimedSerializer:
    """Returns the serializer configured with application secret."""
    return URLSafeTimedSerializer(
        secret_key=settings.SESSION_SECRET,
        salt=SESSION_SALT,
    )


def create_session_token(payload: dict[str, Any]) -> str:
    """Signs payload into a secure token."""
    serializer = get_serializer()
    return str(serializer.dumps(payload))


def verify_session_token(
    token: str, max_age: int = SESSION_MAX_AGE_SECONDS
) -> dict[str, Any] | None:
    """Verifies and decodes token, returning payload dict or None if invalid/expired."""
    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=max_age)
        if isinstance(data, dict):
            return data
        return None
    except (BadSignature, SignatureExpired):
        return None


def set_session_cookie(response: Response, token: str) -> None:
    """Attaches signed session cookie to HTTP response."""
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Deletes session cookie from HTTP response."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
    )
