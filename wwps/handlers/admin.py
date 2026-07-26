from __future__ import annotations

import hmac
import json

from aiohttp import web

from .. import config, dashboard, logging_setup, metrics
from .. import user_data as manage_data

log = logging_setup.get(__name__)

MAX_GRANT = 10_000_000
MAX_REASON = 200
MAX_SEARCH_TERM = 64


class _Denied(Exception):
    def __init__(self, response: web.Response):
        self.response = response


def _json(payload: dict, status: int = 200) -> web.Response:
    return web.json_response(payload, status=status,
                             headers=dashboard.SECURITY_HEADERS)


def _authorized(request: web.Request) -> bool:
    token = config.admin_token
    if not token:
        return False
    provided = request.headers.get("X-Admin-Token") or ""
    return hmac.compare_digest(provided, token)


def _guard(request: web.Request):
    if not config.admin_token:
        return _json({"error": "admin API disabled; set AdminToken in appsettings"},
                     status=503)
    if not _authorized(request):
        metrics.incr("admin_unauthorized")
        log.warning("rejected an admin request from %s on %s",
                    request.remote or "?", request.path)
        return _json({"error": "unauthorized"}, status=401)
    return None


async def _body(request: web.Request) -> dict:
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as ex:
        raise _Denied(_json({"error": "body must be JSON"}, status=400)) from ex
    if not isinstance(body, dict):
        raise _Denied(_json({"error": "body must be a JSON object"}, status=400))
    return body


def _gdkey(body: dict) -> str:
    gdkey = body.get("gdkey")
    if not isinstance(gdkey, str) or not gdkey or len(gdkey) > 64:
        raise _Denied(_json({"error": "gdkey required"}, status=400))
    return gdkey


def _amount(body: dict, key: str) -> int:
    value = body.get(key, 0)
    if isinstance(value, bool):
        raise _Denied(_json({"error": f"{key} must be a whole number"}, status=400))
    try:
        value = int(value)
    except (TypeError, ValueError) as ex:
        raise _Denied(_json({"error": f"{key} must be a whole number"},
                            status=400)) from ex
    if abs(value) > MAX_GRANT:
        raise _Denied(_json({"error": f"{key} is out of range"}, status=400))
    return value


async def _audit(request: web.Request, action: str, gdkey: str, detail: str):
    await manage_data.record_admin_action(
        action, gdkey, detail, request.remote or "unknown")


def admin_route(fn):
    async def wrapper(request: web.Request) -> web.Response:
        denied = _guard(request)
        if denied is not None:
            return denied
        try:
            return await fn(request)
        except _Denied as ex:
            return ex.response
    wrapper.__name__ = fn.__name__
    return wrapper


@admin_route
async def stats(request: web.Request) -> web.Response:
    return _json({
        "accounts": await manage_data.count_accounts(),
        "devices": await manage_data.count_devices(),
        "banned": manage_data.count_bans(),
    })


@admin_route
async def players(request: web.Request) -> web.Response:
    term = request.query.get("q", "")[:MAX_SEARCH_TERM]
    try:
        limit = int(request.query.get("limit") or 20)
    except ValueError:
        return _json({"error": "limit must be a whole number"}, status=400)
    limit = max(1, min(limit, 100))
    return _json({"players": await manage_data.search_accounts(term, limit)})


@admin_route
async def player(request: web.Request) -> web.Response:
    summary = await manage_data.admin_player_summary(request.match_info["gdkey"])
    if summary is None:
        return _json({"error": "not found"}, status=404)
    return _json(summary)


@admin_route
async def grant(request: web.Request) -> web.Response:
    body = await _body(request)
    gdkey = _gdkey(body)
    ymoney = _amount(body, "ymoney")
    hitodama = _amount(body, "hitodama")
    result = await manage_data.admin_adjust(gdkey, ymoney, hitodama)
    if result is None:
        return _json({"error": "not found"}, status=404)
    metrics.incr("admin_grants")
    metrics.event("warning", f"admin granted {ymoney} ymoney / {hitodama} hitodama "
                             f"to {logging_setup.mask(gdkey)}")
    log.info("admin grant to %s: ymoney=%s hitodama=%s",
             logging_setup.mask(gdkey), ymoney, hitodama)
    await _audit(request, "grant", gdkey, f"ymoney={ymoney} hitodama={hitodama}")
    return _json({"ok": True, "result": result})


@admin_route
async def ban(request: web.Request) -> web.Response:
    body = await _body(request)
    gdkey = _gdkey(body)
    reason = body.get("reason") or "banned by an administrator"
    if not isinstance(reason, str):
        return _json({"error": "reason must be text"}, status=400)
    reason = reason[:MAX_REASON]
    await manage_data.add_ban(gdkey, reason)
    metrics.incr("admin_bans")
    metrics.event("serious", f"admin banned {logging_setup.mask(gdkey)}: {reason}")
    log.warning("admin banned %s: %s", logging_setup.mask(gdkey), reason)
    await _audit(request, "ban", gdkey, reason)
    return _json({"ok": True})


@admin_route
async def unban(request: web.Request) -> web.Response:
    body = await _body(request)
    gdkey = _gdkey(body)
    removed = await manage_data.remove_ban(gdkey)
    metrics.event("good", f"admin unbanned {logging_setup.mask(gdkey)}")
    log.info("admin unbanned %s", logging_setup.mask(gdkey))
    await _audit(request, "unban", gdkey, "")
    return _json({"ok": True, "removed": removed})
