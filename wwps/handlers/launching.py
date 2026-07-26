from __future__ import annotations

import json
import re
import time

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
    """The base URL handed to the client for its asset and API calls.

    Forwarded headers decide where players' clients will send everything that
    follows, so they are only believed when the operator has said a proxy sits
    in front of this server.
    """
    if config.public_url:
        return config.public_url.rstrip("/")
    if config.trust_proxy_headers:
        proto = request.headers.get("X-Forwarded-Proto")
        host = request.headers.get("X-Forwarded-Host")
        if host:
            return f"{proto or request.scheme}://{host.split(',')[0].strip()}".rstrip("/")
    return str(request.url.origin()).rstrip("/")


def _force_https(body: str) -> str:
    return re.sub(r'"http://([^"]+)"', r'"https://\1"', body)


def _freshen(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if payload.get("lncNotices"):
        payload["lncNotices"] = []
    payload["currentTime"] = int(time.time() * 1000)
    return json.dumps(payload)


async def launching(request: web.Request) -> web.Response:
    template = _load_template()
    if template is None:
        log.error("hspLaunchingInfos not found in game data")
        return web.json_response({"state": 1, "stateMessage": "config missing",
                                  "loginable": "N", "playable": "N"}, status=200)
    base = _public_base(request)
    body = template.replace(PLACEHOLDER_HOST, base)
    if base.startswith("https://"):
        body = _force_https(body)
    body = _freshen(body)
    metrics.incr("launching_served")
    log.debug("served launching info to %s (base %s)", request.remote or "?", base)
    return web.Response(text=body, content_type="application/json")
