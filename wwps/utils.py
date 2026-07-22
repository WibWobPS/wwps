from __future__ import annotations

import json

from aiohttp import web

from . import config, game_data, logging_setup, metrics, nhn_crypt, user_data

log = logging_setup.get(__name__)


def bad_request() -> web.Response:
    return web.Response(status=400, text="Bad request", content_type="text/plain")


def encrypted_json(obj, status: int = 200) -> web.Response:
    payload = obj if isinstance(obj, str) else json.dumps(obj, separators=(',', ':'), ensure_ascii=False)
    return web.Response(status=status, text=nhn_crypt.encrypt_response(payload),
                        content_type="application/json")


async def read_decrypted_request(request: web.Request) -> dict:
    from . import security
    body = (await request.read()).decode("utf-8")
    payload = json.loads(nhn_crypt.decrypt_request(body))
    await security.enforce_ownership(payload, request.path)
    return payload


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
