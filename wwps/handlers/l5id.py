from __future__ import annotations

import time

from aiohttp import web

from .. import config, logging_setup, metrics, user_data, validate

log = logging_setup.get(__name__)


def _key(value: str) -> dict:
    return {"value": value, "signature": ""}


def _device_id(request: web.Request, field: str) -> str | None:
    value = request.query.get(field, "")
    return value if validate.is_key_like(value) else None


def _unknown_udkey(status: int = 200) -> web.Response:
    return web.json_response(
        {"result": False, "code": 4009, "message": "Unknown UDKey"}, status=status)


async def _active_response(udkey_value: str) -> dict:
    gdkeys = [_key(k) for k in await user_data.get_gdkeys_from_udkey(udkey_value)]
    udkey = _key(udkey_value)
    return {
        "result": True,
        "keys": [{"udkey": udkey, "gdkeys": gdkeys}],
        "udkey": udkey,
        "gdkeys": gdkeys,
        "is_linked": False,
        "max_gdkeys": config.max_gdkeys_per_device,
        "rc_client_version": {"1": "", "2": ""},
        "sign_timestamp": int(time.time() * 1000),
        "sign_nonce": "123",
        "is_created": False,
    }


async def active_puni(request: web.Request) -> web.Response:
    udkey = request.query.get("udkey")
    if udkey is None:
        udkey = await user_data.new_device()
        metrics.incr("devices_created")
    elif not validate.is_key_like(udkey):
        return _unknown_udkey(400)
    return web.json_response(await _active_response(udkey))


async def active_wibwob(request: web.Request) -> web.Response:
    udkey = _device_id(request, "TICKET")
    if udkey is None:
        return _unknown_udkey(400)
    if not await user_data.is_device_exists(udkey):
        await user_data.new_device(udkey)
        metrics.incr("devices_created")
    return web.json_response(await _active_response(udkey))


async def create_gdkey(request: web.Request) -> web.Response:
    udkey = _device_id(request, "udkey")
    if udkey is None or not await user_data.is_device_exists(udkey):
        return _unknown_udkey()

    existing = await user_data.get_gdkeys_from_udkey(udkey)
    if len(existing) >= config.max_gdkeys_per_device:
        metrics.incr("gdkey_limit_reached")
        log.warning("device %s already holds %d save(s)",
                    logging_setup.mask(udkey), len(existing))
        return web.json_response(
            {"result": False, "code": 4010,
             "message": "This device already holds the maximum number of saves"})

    gdkey = await user_data.new_account()
    await user_data.add_account_to_device(udkey, gdkey)
    metrics.incr("gdkeys_created")
    return web.json_response({
        "result": True,
        "gdkey": _key(gdkey),
        "sign_nonce": "123",
        "sign_timestamp": int(time.time() * 1000),
    })
