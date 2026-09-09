"""Login attempt throttling (cache-backed, no extra dependency)."""
from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    return request.META.get("REMOTE_ADDR") or "unknown"


def _keys(request, username: str):
    uname = (username or "").strip().lower()
    ip = client_ip(request)
    return f"login-fail:{ip}:{uname}", f"login-lock:{ip}:{uname}"


def is_locked(request, username: str) -> bool:
    _, lock_key = _keys(request, username)
    return bool(cache.get(lock_key))


def record_failure(request, username: str) -> bool:
    """Increment failures. Returns True if the account/IP is now locked."""
    fail_key, lock_key = _keys(request, username)
    window = getattr(settings, "LOGIN_FAILURE_WINDOW", 600)
    max_fail = getattr(settings, "LOGIN_MAX_FAILURES", 5)
    lockout = getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900)
    count = int(cache.get(fail_key) or 0) + 1
    cache.set(fail_key, count, window)
    if count >= max_fail:
        cache.set(lock_key, True, lockout)
        return True
    return False


def clear_failures(request, username: str) -> None:
    fail_key, lock_key = _keys(request, username)
    cache.delete(fail_key)
    cache.delete(lock_key)
