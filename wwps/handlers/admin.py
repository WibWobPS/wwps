from __future__ import annotations

import json

from aiohttp import web

from .. import config, logging_setup, metrics
from .. import user_data as manage_data

log = logging_setup.get(__name__)


def _authorized(request: web.Request) -> bool:
    token = config.admin_token
    if not token:
        return False
    provided = (request.query.get("token")
                or request.headers.get("X-Admin-Token"))
    return provided == token


def _guard(request: web.Request):
    if not config.admin_token:
        return web.json_response(
            {"error": "admin API disabled; set AdminToken in appsettings"},
            status=503)
    if not _authorized(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    return None


async def stats(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    return web.json_response({
        "accounts": await manage_data.count_accounts(),
        "devices": await manage_data.count_devices(),
        "banned": len(manage_data._bans),
    })


async def players(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    term = request.query.get("q", "")
    limit = min(int(request.query.get("limit", 20) or 20), 100)
    results = await manage_data.search_accounts(term, limit)
    return web.json_response({"players": results})


async def player(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    summary = await manage_data.admin_player_summary(request.match_info["gdkey"])
    if summary is None:
        return web.json_response({"error": "not found"}, status=404)
    return web.json_response(summary)


async def grant(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    body = await request.json()
    gdkey = body.get("gdkey")
    if not gdkey:
        return web.json_response({"error": "gdkey required"}, status=400)
    result = await manage_data.admin_adjust(
        gdkey, int(body.get("ymoney", 0)), int(body.get("hitodama", 0)))
    if result is None:
        return web.json_response({"error": "not found"}, status=404)
    metrics.incr("admin_grants")
    metrics.event("warning",
                  f"admin granted {body.get('ymoney', 0)} ymoney / "
                  f"{body.get('hitodama', 0)} hitodama to {gdkey[:8]}")
    log.info("admin grant to %s: ymoney=%s hitodama=%s", gdkey,
             body.get("ymoney", 0), body.get("hitodama", 0))
    return web.json_response({"ok": True, "result": result})


async def ban(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    body = await request.json()
    gdkey = body.get("gdkey")
    if not gdkey:
        return web.json_response({"error": "gdkey required"}, status=400)
    reason = body.get("reason", "banned by an administrator")
    await manage_data.add_ban(gdkey, reason)
    metrics.incr("admin_bans")
    metrics.event("serious", f"admin banned {gdkey[:8]}: {reason}")
    log.warning("admin banned %s: %s", gdkey, reason)
    return web.json_response({"ok": True})


async def unban(request: web.Request) -> web.Response:
    denied = _guard(request)
    if denied is not None:
        return denied
    body = await request.json()
    gdkey = body.get("gdkey")
    if not gdkey:
        return web.json_response({"error": "gdkey required"}, status=400)
    removed = await manage_data.remove_ban(gdkey)
    metrics.event("good", f"admin unbanned {gdkey[:8]}")
    log.info("admin unbanned %s", gdkey)
    return web.json_response({"ok": True, "removed": removed})
