"""In-memory sliding window rate limiter for login attempts (spec/07 §7.4, failed attempts per IP and username)."""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from backend.app.config import settings

MAX_LOGIN_ATTEMPTS_PER_MINUTE = settings.MAX_LOGIN_ATTEMPTS_PER_MINUTE
LOGIN_RATE_LIMIT_WINDOW_SECONDS = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS

# Failed attempts only, never successes: per (IP, username) and, as a spray guard, per IP.
_login_failures: dict[str, list[float]] = defaultdict(list)
_login_failures_by_ip: dict[str, list[float]] = defaultdict(list)


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


def _recent(bucket: dict[str, list[float]], key: str) -> list[float]:
    cutoff = time.monotonic() - float(settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    recent = [t for t in bucket[key] if t > cutoff]
    bucket[key] = recent
    return recent


def _user_key(request: Request, username: str | None) -> str:
    name = str(username or "").strip().lower()[:64]
    return f"{get_client_ip(request)}|{name}"


def check_login_allowed(request: Request, username: str | None) -> None:
    """Raises 429 when this IP has too many recent FAILED logins for this username (or too many
    failures across usernames). Successful logins never count, so judges who share one network
    and the shared demo accounts are not locked out; wrong passwords still are."""
    ip = get_client_ip(request)
    if (
        len(_recent(_login_failures, _user_key(request, username)))
        >= settings.MAX_LOGIN_ATTEMPTS_PER_MINUTE
        or len(_recent(_login_failures_by_ip, ip)) >= settings.MAX_LOGIN_FAILURES_PER_IP_PER_MINUTE
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again after 1 minute.",
        )


def record_login_failure(request: Request, username: str | None) -> None:
    now = time.monotonic()
    _login_failures[_user_key(request, username)].append(now)
    _login_failures_by_ip[get_client_ip(request)].append(now)


def clear_login_failures(request: Request, username: str | None) -> None:
    """A correct password clears that (IP, username) failure count."""
    _login_failures.pop(_user_key(request, username), None)


def reset_login_rate_limits() -> None:
    """Resets rate limit state (used in tests)."""
    _login_failures.clear()
    _login_failures_by_ip.clear()


_chat_attempts: dict[str, list[float]] = defaultdict(list)


def check_chat_rate_limit(user_key: str) -> None:
    """Per-user sliding window on chat sends (each send can trigger STT, LLM and TTS calls)."""
    now = time.monotonic()
    cutoff = now - float(settings.CHAT_RATE_LIMIT_WINDOW_SECONDS)
    attempts = [t for t in _chat_attempts[user_key] if t > cutoff]
    if len(attempts) >= settings.CHAT_MAX_MESSAGES_PER_MINUTE:
        _chat_attempts[user_key] = attempts
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many messages. Please wait a minute.",
        )
    attempts.append(now)
    _chat_attempts[user_key] = attempts


_translate_attempts: dict[str, list[float]] = defaultdict(list)


def check_translate_rate_limit(user_key: str) -> None:
    """Per-user sliding window on translations that need an LLM call (cache hits are free)."""
    now = time.monotonic()
    cutoff = now - float(settings.TRANSLATE_RATE_LIMIT_WINDOW_SECONDS)
    attempts = [t for t in _translate_attempts[user_key] if t > cutoff]
    if len(attempts) >= settings.TRANSLATE_MAX_REQUESTS_PER_MINUTE:
        _translate_attempts[user_key] = attempts
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many translation requests. Please wait a minute.",
        )
    attempts.append(now)
    _translate_attempts[user_key] = attempts


def reset_translate_rate_limits() -> None:
    """Resets translate rate limit state (used in tests)."""
    _translate_attempts.clear()


def reset_chat_rate_limits() -> None:
    """Resets chat rate limit state (used in tests)."""
    _chat_attempts.clear()
