from __future__ import annotations

import time

from aiohttp import web

from . import config, logging_setup, metrics

log = logging_setup.get(__name__)

MAX_TRACKED_CLIENTS = 20_000
SWEEP_INTERVAL = 60.0

# Paths that create rows, send mail or expose operator data. They get the
# strict budget; everything else gets the gameplay budget.
STRICT_PREFIXES = ("/auth/", "/admin/", "/l5id/", "/api/v1/")
STRICT_PATHS = ("/serialConfirm.nhn", "/createUser.nhn", "/deleteUser.nhn",
                "/conflate.nhn")

EXEMPT_PREFIXES = ("/healthz", "/readyz", "/dd/")


class _Bucket:
    __slots__ = ("tokens", "updated")

    def __init__(self, tokens: float, updated: float):
        self.tokens = tokens
        self.updated = updated


_buckets: dict[tuple[str, str], _Bucket] = {}
_last_sweep = 0.0


def reset():
    _buckets.clear()
    global _last_sweep
    _last_sweep = 0.0


def _sweep(now: float):
    global _last_sweep
    if now - _last_sweep < SWEEP_INTERVAL:
        return
    _last_sweep = now
    stale = [key for key, bucket in _buckets.items()
             if now - bucket.updated > SWEEP_INTERVAL * 5]
    for key in stale:
        del _buckets[key]
    if len(_buckets) > MAX_TRACKED_CLIENTS:
        oldest = sorted(_buckets.items(), key=lambda kv: kv[1].updated)
        for key, _ in oldest[:len(_buckets) - MAX_TRACKED_CLIENTS]:
            del _buckets[key]


def _tier(path: str) -> str | None:
    if path.startswith(EXEMPT_PREFIXES):
        return None
    if path.startswith(STRICT_PREFIXES) or path in STRICT_PATHS:
        return "strict"
    return "normal"


def _budget(tier: str) -> tuple[float, float]:
    if tier == "strict":
        per_minute = max(1, config.rate_limit_auth_per_minute)
        return per_minute / 60.0, float(max(1, min(per_minute, 10)))
    per_minute = max(1, config.rate_limit_per_minute)
    return per_minute / 60.0, float(max(1, config.rate_limit_burst))


def client_key(request: web.Request) -> str:
    if config.trust_proxy_headers:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return (request.remote or "unknown")[:64]


def allow(tier: str, client: str, now: float | None = None) -> bool:
    if not config.rate_limit_enabled:
        return True
    now = time.monotonic() if now is None else now
    _sweep(now)
    rate, capacity = _budget(tier)
    key = (tier, client)
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = _Bucket(capacity, now)
        _buckets[key] = bucket
    else:
        bucket.tokens = min(capacity, bucket.tokens + (now - bucket.updated) * rate)
        bucket.updated = now
    if bucket.tokens < 1.0:
        return False
    bucket.tokens -= 1.0
    return True


def retry_after(tier: str) -> int:
    rate, _ = _budget(tier)
    return max(1, int(1.0 / rate))


@web.middleware
async def middleware(request: web.Request, handler):
    tier = _tier(request.path)
    if tier is None or not config.rate_limit_enabled:
        return await handler(request)
    client = client_key(request)
    if not allow(tier, client):
        metrics.incr("rate_limited")
        log.warning("rate limited %s on %s", client, request.path)
        return web.json_response(
            {"error": "too many requests"}, status=429,
            headers={"Retry-After": str(retry_after(tier))})
    return await handler(request)
