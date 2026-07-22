from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wwps import config, game_data, metrics, security
from wwps import user_data as manage_data

FAKE_TABLES = {
    "mstVersionMaster": "16774",
    "ymoneyShopSaleList": "[5]",
    "shopSaleList": "[1]",
    "hitodamaShopSaleList": "[2]",
    "noticePageList": "[]",
    "responseCodeTeamEvent": "0",
    "ywp_mst_version_master": "1|1",
    "ywp_mst_event": "[]",
    "ywp_mst_shop_hitodama_list": json.dumps(
        {"data": [{"goodsId": 1, "price": 100, "sellCnt": 5, "bonusCnt": 1}]}),
    "ywp_mst_map": json.dumps({"data": [{
        "mapId": 1001, "mapName": "Test", "needYmoney": 0, "needYoukaiId": 0,
        "needYoukaiLevel": 0, "needFriendPoint": 0, "nextMapId": 0,
        "extraMapId": 0, "reverseMapId": 0, "textUnlock": ""}]}),
    "ywp_mst_youkai_level": json.dumps({"tableData": "1|1|0|99*1|2|100|299*1|3|300|699"}),
    "ywp_mst_youkai": json.dumps({"tableData":
        "2235000|Tester|1|1|1|1|1|10|100|500|20|120|2235001|5|1|||||||0|0|0|0|0|0|0|0|0|0||0|0|0||||0"}),
}


@pytest.fixture(autouse=True)
def game_config(tmp_path):
    settings = tmp_path / "appsettings.json"
    settings.write_text(json.dumps({
        "PostgresConnectionString": "postgresql://localhost/none",
        "IsWibWob": True,
        "GameVersion": "1.0.0",
        "ServerName": "WWPS test",
        "DataDownloadURL": "http://localhost/dd",
        "EnforceAccountOwnership": True,
        "ValidateBefriend": True,
    }))
    config.static_init(str(settings))
    game_data.gamedata_cache.clear()
    game_data.gamedata_cache.update(FAKE_TABLES)
    metrics.reset()
    security.clear_ownership_cache()
    yield


@pytest.fixture
def store(monkeypatch):
    data: dict[str, dict] = {}
    devices: dict[str, list[str]] = {}

    async def get_ywp_user(gdkey, table):
        return data.get(gdkey, {}).get(table)

    async def set_ywp_user(gdkey, table, value):
        data.setdefault(gdkey, {})[table] = value

    async def get_entire_user_data(gdkey):
        return data.get(gdkey, {})

    async def get_device_gdkeys(udkey):
        return devices.get(udkey)

    async def get_account_from_gdkey(gdkey):
        return None

    monkeypatch.setattr(manage_data, "get_ywp_user", get_ywp_user)
    monkeypatch.setattr(manage_data, "set_ywp_user", set_ywp_user)
    monkeypatch.setattr(manage_data, "get_entire_user_data", get_entire_user_data)
    monkeypatch.setattr(manage_data, "get_device_gdkeys", get_device_gdkeys)
    monkeypatch.setattr(manage_data, "get_account_from_gdkey", get_account_from_gdkey)
    return {"tables": data, "devices": devices}
