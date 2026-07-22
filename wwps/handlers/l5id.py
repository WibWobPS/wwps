from __future__ import annotations

import json
import secrets
import time

from aiohttp import web

from .. import user_data


def _key(value: str) -> dict:
    return {"value": value, "signature": ""}


async def _active_response(udkey_value: str) -> dict:
    gdkeys = [_key(k) for k in await user_data.get_gdkeys_from_udkey(udkey_value)]
    udkey = _key(udkey_value)
    return {
        "result": True,
        "keys": [{"udkey": udkey, "gdkeys": gdkeys}],
        "udkey": udkey,
        "gdkeys": gdkeys,
        "is_linked": False,
        "max_gdkeys": 3,
        "rc_client_version": {"1": "", "2": ""},
        "sign_timestamp": int(time.time() * 1000),
        "sign_nonce": "123",
        "is_created": False,
    }


async def active_puni(request: web.Request) -> web.Response:
    udkey = request.query.get("udkey")
    if udkey is None:
        udkey = await user_data.new_device()
    res = await _active_response(udkey)
    return web.json_response(res)


async def active_wibwob(request: web.Request) -> web.Response:
    udkey = request.query.get("TICKET", "")
    if not await user_data.is_device_exists(udkey):
        await user_data.new_device(udkey)
    res = await _active_response(udkey)
    return web.json_response(res)


async def create_gdkey(request: web.Request) -> web.Response:
    if "udkey" not in request.query:
        bad = {"result": False, "code": 4009, "message": "Unknown UDKey"}
        return web.json_response(bad)
    gdkey = await user_data.new_account()
    await user_data.add_account_to_device(request.query["udkey"], gdkey)
    res = {
        "result": True,
        "gdkey": _key(gdkey),
        "sign_nonce": "123",
        "sign_timestamp": int(time.time() * 1000),
    }
    return web.json_response(res)
