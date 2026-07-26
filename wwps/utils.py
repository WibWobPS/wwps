from __future__ import annotations

import json

from aiohttp import web

from . import game_data, logging_setup, metrics, nhn_crypt, user_data

log = logging_setup.get(__name__)


SAVE_LOCK = web.RequestKey("save_lock") if hasattr(web, "RequestKey") else "save_lock"


class MalformedRequestError(Exception):
    pass


def bad_request() -> web.Response:
    return web.Response(status=400, text="Bad request", content_type="text/plain")


def encrypted_json(obj, status: int = 200) -> web.Response:
    payload = obj if isinstance(obj, str) else json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
    return web.Response(status=status, text=nhn_crypt.encrypt_response(payload),
                        content_type="application/json")


async def read_decrypted_request(request: web.Request) -> dict:
    from . import security
    try:
        body = (await request.read()).decode("utf-8")
        payload = json.loads(nhn_crypt.decrypt_request(body))
    except Exception as ex:
        log.warning("could not decode a request on %s: %s", request.path, ex)
        raise MalformedRequestError(str(ex)) from ex
    if not isinstance(payload, dict):
        raise MalformedRequestError("payload is not an object")
    await security.enforce_ownership(payload, request.path)
    await _hold_save_lock(request, payload)
    return payload


async def _hold_save_lock(request: web.Request, payload: dict):
    """Take the save's request lock for the rest of this request.

    Handlers read a table, await, then write it back. Two requests for one save
    running at once would each read the pre-request balance, so a player could
    spend the same Y-Money twice by firing them in parallel.
    """
    from . import security
    gdkey, _ = security.extract_keys(payload)
    if not gdkey or request.get(SAVE_LOCK) is not None:
        return
    lock = user_data.request_lock(gdkey)
    await lock.acquire()
    request[SAVE_LOCK] = lock


async def add_tables_to_response(tables, result: dict, is_download_once: bool,
                                 gdkey: str = ""):
    user_tables = None
    if is_download_once and gdkey:
        user_tables = await user_data.get_entire_user_data(gdkey)

    for table in tables:
        table_text = None
        table_obj = None
        if table.startswith("ywp_user"):
            if not gdkey:
                continue
            if is_download_once and user_tables is not None:
                table_obj = user_tables.get(table)
            else:
                table_obj = await user_data.get_ywp_user(gdkey, table)
        elif table in game_data.gamedata_cache:
            table_text = game_data.gamedata_cache[table]
        else:
            log.warning("table not found: %s", table)
            metrics.incr("table_missing")
            continue

        if table_text is not None:
            try:
                table_obj = json.loads(table_text)
                if isinstance(table_obj, dict):
                    if "data" in table_obj:
                        table_obj = table_obj["data"]
                    elif "tableData" in table_obj:
                        table_obj = table_obj["tableData"]
            except (json.JSONDecodeError, ValueError):
                table_obj = table_text
        result[table] = table_obj
