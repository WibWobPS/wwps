from __future__ import annotations

import time
from datetime import datetime

from . import config, game_data
from .rows import LotYoukaiInfoRow, TutorialEntryRow, parser_for


def common_response_dict() -> dict:
    return {
        "serverDt": int(time.time() * 1000),
        "mstVersionMaster": int(game_data.gamedata_cache["mstVersionMaster"]),
        "ymoneyShopSaleList": game_data.deserialize_gamedata("ymoneyShopSaleList"),
        "ywpToken": "",
        "token": "",
        "dialogMsg": "",
        "webServerIp": "https:\\/\\/gameserver.yw-p.com",
        "dialogTitle": "",
        "storeUrl": "",
    }


def common_response_full(result_code=0, next_screen_type=0, result_type=0) -> dict:
    return {
        "serverDt": int(time.time() * 1000),
        "resultCode": result_code,
        "nextScreenType": next_screen_type,
        "resultType": result_type,
        "mstVersionMaster": int(game_data.gamedata_cache["mstVersionMaster"]),
        "shopSaleList": None,
        "ymoneyShopSaleList": game_data.deserialize_gamedata("ymoneyShopSaleList"),
        "hitodamaShopSaleList": None,
        "ywpToken": "",
        "token": "",
        "dialogMsg": "",
        "webServerIp": "https:\\/\\/gameserver.yw-p.com",
        "dialogTitle": "",
        "storeUrl": "",
        "mstVersionVer": 0,
    }


def modi_dt(now: datetime | None = None) -> dict:
    now = now or datetime.now()
    utc_offset = -int((now.astimezone().utcoffset() or 0).total_seconds() // 60) \
        if now.tzinfo is None else -int(now.utcoffset().total_seconds() // 60)
    return {
        "date": now.day,
        "day": (now.weekday() + 1) % 7,
        "hours": now.hour,
        "minutes": now.minute,
        "month": now.month,
        "seconds": now.second,
        "time": int(now.timestamp() * 1000) if now.tzinfo else int(time.mktime(now.timetuple()) * 1000),
        "timezoneOffset": utc_offset,
        "year": now.year - 1900,
    }


def self_rank(user_data) -> dict:
    return {
        "rankStart": 1,
        "score": 0,
        "leagueId": 5,
        "rank": 0,
        "groupNo": 0,
        "remainSec": 0,
        "leagueChangeStatus": 0,
        "userId": user_data.userId,
    }


class TutorialList:

    def __init__(self, entries: list[dict] | None = None):
        self.entries: list[dict] = entries if entries is not None else []

    @classmethod
    def parse(cls, obj) -> "TutorialList":
        if isinstance(obj, list):
            return cls([dict(e) for e in obj])
        if isinstance(obj, str):
            prsr = parser_for(TutorialEntryRow, obj)
            return cls([{
                "tutorialType": it.TutorialType,
                "tutorialId": it.TutorialId,
                "tutorialStatus": it.TutorialStatus,
                "firstClear": it.FirstClear,
            } for it in prsr.items])
        raise ValueError("tutorial list is in wrong format")

    def serialize(self):
        if config.is_wibwob:
            return self.entries
        prsr = parser_for(TutorialEntryRow, "")
        for e in self.entries:
            prsr.add_item(TutorialEntryRow(
                TutorialType=e.get("tutorialType", 0),
                TutorialId=e.get("tutorialId", 0),
                TutorialStatus=e.get("tutorialStatus", 0),
                FirstClear=e.get("firstClear", 0)))
        return str(prsr)

    def get_tutorial_flg_index(self, tutorial_id: int, tutorial_type: int) -> int:
        for i, e in enumerate(self.entries):
            if e.get("tutorialId") == tutorial_id and e.get("tutorialType") == tutorial_type:
                return i
        return -1

    def edit_tutorial_flg(self, tutorial_type: int, tutorial_id: int, value: int):
        idx = self.get_tutorial_flg_index(tutorial_id, tutorial_type)
        if idx == -1:
            self.entries.append({"tutorialType": tutorial_type,
                                 "tutorialId": tutorial_id,
                                 "tutorialStatus": value,
                                 "firstClear": 0})
        else:
            self.entries[idx]["tutorialStatus"] = value
            self.entries[idx]["tutorialType"] = tutorial_type

    def get_status(self, tutorial_id: int, tutorial_type: int) -> int:
        idx = self.get_tutorial_flg_index(tutorial_id, tutorial_type)
        if idx == -1:
            return -1
        return self.entries[idx].get("tutorialStatus", 0)


class LotYoukaiInfoList:

    def __init__(self, entries: list[dict] | None = None):
        self.entries: list[dict] = entries if entries is not None else []

    @classmethod
    def parse(cls, obj) -> "LotYoukaiInfoList":
        if isinstance(obj, list):
            return cls([dict(e) for e in obj])
        if isinstance(obj, str):
            prsr = parser_for(LotYoukaiInfoRow, obj)
            return cls([{"lotPattern": it.LotPattern, "lotResult": it.LotResult}
                        for it in prsr.items])
        raise ValueError("Bad lotYoukaiInfoList")

    def serialize(self):
        if config.is_wibwob:
            return self.entries
        prsr = parser_for(LotYoukaiInfoRow, "")
        for e in self.entries:
            prsr.add_item(LotYoukaiInfoRow(LotPattern=e.get("lotPattern", ""),
                                           LotResult=e.get("lotResult", "")))
        return str(prsr)
