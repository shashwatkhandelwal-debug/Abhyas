"""Double-submit cookie CSRF protection for HTML forms (spec/07 §7.4)."""

import hmac
import secrets

from fastapi import HTTPException, Request, Response, status

from backend.app.config import settings

CSRF_COOKIE_NAME = "abhyas_csrf"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_FORM_FIELD = "csrf_token"


def generate_csrf_token() -> str:
    """Generates a cryptographically strong CSRF token."""
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response: Response, token: str) -> None:
    """Sets the double-submit CSRF cookie."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        max_age=86400,  # 24 hours
        httponly=False,  # Accessible to client scripts if needed
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        path="/",
    )


async def verify_csrf_token(request: Request) -> None:
    """Verifies that the CSRF cookie matches the submitted token in header or form body."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF सुरक्षा टोकन अनुपस्थित है (CSRF token missing)",
        )

    # Check header first (common for JSON/fetch requests)
    submitted_token = request.headers.get(CSRF_HEADER_NAME)

    # If not in header, check form data
    if not submitted_token:
        content_type = request.headers.get("content-type", "")
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            try:
                form = await request.form()
                form_val = form.get(CSRF_FORM_FIELD)
                if isinstance(form_val, str):
                    submitted_token = form_val
            except Exception:
                submitted_token = None

    if not submitted_token or not hmac.compare_digest(cookie_token, submitted_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="अमान्य CSRF सुरक्षा टोकन (Invalid CSRF token)",
        )
