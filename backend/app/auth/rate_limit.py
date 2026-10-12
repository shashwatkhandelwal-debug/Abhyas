"""In-memory sliding window rate limiter for login attempts (spec/07 §7.4: 5/min/IP)."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

MAX_LOGIN_ATTEMPTS_PER_MINUTE = 5
WINDOW_SECONDS = 60.0

# Store list of attempt timestamps per IP
_login_attempts: dict[str, list[float]] = defaultdict(list)


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For if behind reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in chain is original client
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def check_login_rate_limit(request: Request) -> None:
    """Enforces 5 attempts per minute per IP limit on login route."""
    ip = get_client_ip(request)
    now = time.monotonic()
    cutoff = now - WINDOW_SECONDS

    # Prune old timestamps
    attempts = [t for t in _login_attempts[ip] if t > cutoff]
    _login_attempts[ip] = attempts

    if len(attempts) >= MAX_LOGIN_ATTEMPTS_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="बहुत अधिक लॉगिन प्रयास। कृपया 1 मिनट बाद पुनः प्रयास करें (Too many login attempts. Please try again after 1 minute.)",
        )

    # Record current attempt
    _login_attempts[ip].append(now)


def reset_login_rate_limits() -> None:
    """Resets rate limit state (used in tests)."""
    _login_attempts.clear()
