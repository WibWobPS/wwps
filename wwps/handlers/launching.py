from __future__ import annotations

import json

from aiohttp import web

from .. import config, game_data, logging_setup, metrics

log = logging_setup.get(__name__)

PLACEHOLDER_HOST = "http://youtube.com"

_template: str | None = None


def _load_template() -> str | None:
    global _template
    if _template is None:
        raw = game_data.gamedata_cache.get("hspLaunchingInfos")
        if raw is None:
            return None
        _template = raw
    return _template


def _public_base(request: web.Request) -> str:
    if config.public_url:
        return config.public_url.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto")
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    if host:
        scheme = proto or request.scheme
        return f"{scheme}://{host}".rstrip("/")
    return str(request.url.origin()).rstrip("/")


async def launching(request: web.Request) -> web.Response:
    template = _load_template()
    if template is None:
        log.error("hspLaunchingInfos not found in game data")
        return web.json_response({"state": 1, "stateMessage": "config missing",
                                  "loginable": "N", "playable": "N"}, status=200)
    base = _public_base(request)
    body = template.replace(PLACEHOLDER_HOST, base)
    metrics.incr("launching_served")
    log.info("served launching info to %s (base %s)",
             request.remote or "?", base)
    return web.Response(text=body, content_type="application/json")
