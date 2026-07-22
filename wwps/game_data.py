from __future__ import annotations

import json
import os

from . import config
from . import logging_setup, metrics

log = logging_setup.get(__name__)

gamedata_cache: dict[str, str] = {}


def init():
    gamedata_cache.clear()
    res_dir = config.RESOURCES_DIR
    if not os.path.isdir(res_dir):
        log.warning("resources directory not found at %s, "
                    "static game tables will be missing", res_dir)
        return
    for name in os.listdir(res_dir):
        if not name.endswith(".txt"):
            continue
        path = os.path.join(res_dir, name)
        with open(path, encoding="utf-8") as f:
            gamedata_cache[name[:-len(".txt")]] = f.read()


def get_table_string_from_json(table_id: str) -> str:
    raw = gamedata_cache[table_id]
    return json.loads(raw)["tableData"]


def deserialize_gamedata(gamedata_name: str):
    out = json.loads(gamedata_cache[gamedata_name])
    if out is None:
        raise ValueError(f"{gamedata_name} static gamedata is invalid")
    return out
