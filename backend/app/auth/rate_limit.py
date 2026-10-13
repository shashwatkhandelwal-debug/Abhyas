"""In-memory sliding window rate limiter for login attempts (spec/07 §7.4: 5/min/IP)."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from backend.app.config import settings

MAX_LOGIN_ATTEMPTS_PER_MINUTE = settings.MAX_LOGIN_ATTEMPTS_PER_MINUTE
LOGIN_RATE_LIMIT_WINDOW_SECONDS = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS

# Store list of attempt timestamps per IP
_login_attempts: dict[str, list[float]] = defaultdict(list)


def get_client_ip(request: Request) -> str:
    """Extracts client IP, respecting X-Forwarded-For in production or via trusted proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if settings.ENVIRONMENT == "production":
        if forwarded:
            hops = forwarded.split(",")
            return hops[-1].strip()
        return request.client.host if request.client and request.client.host else "127.0.0.1"

    direct_ip = request.client.host if request.client and request.client.host else "127.0.0.1"
    trusted_proxies = {ip.strip() for ip in settings.TRUSTED_PROXY_IPS.split(",") if ip.strip()}

    if direct_ip in trusted_proxies and forwarded:
        return forwarded.split(",")[0].strip()
    return direct_ip


def check_login_rate_limit(request: Request) -> None:
    """Enforces rate limit per IP on login route using settings constants."""
    ip = get_client_ip(request)
    now = time.monotonic()
    cutoff = now - float(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)

    # Prune old timestamps
    attempts = [t for t in _login_attempts[ip] if t > cutoff]
    _login_attempts[ip] = attempts

    if len(attempts) >= settings.MAX_LOGIN_ATTEMPTS_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="बहुत अधिक लॉगिन प्रयास। कृपया 1 मिनट बाद पुनः प्रयास करें (Too many login attempts. Please try again after 1 minute.)",
        )

    # Record current attempt
    _login_attempts[ip].append(now)


def reset_login_rate_limits() -> None:
    """Resets rate limit state (used in tests)."""
    _login_attempts.clear()
