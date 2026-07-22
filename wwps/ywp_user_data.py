from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from . import user_data as manage_data

TIME_FORMAT = "%Y-%m-%d %H:%M:%S %z"
HITODAMA_RECOVER_TABLE = "last_hitodama_recover"
HITODAMA_RECOVER_SEC = 900
FREE_HITODAMA_MAX = 5

_FIELDS = {
    "birthday": "",
    "freeHitodama": 0,
    "friendMaxCnt": 0,
    "youkaiId": 0,
    "medalPoint": 0,
    "nowStageId": 0,
    "titleId": 0,
    "gokuCollectCnt": 0,
    "ymoney": 0,
    "reviewFlg": 0,
    "moveReason": 0,
    "chargeYmoney": 0,
    "crystalCollectCnt": 0,
    "eventPointUpItemId": 0,
    "characterId": "",
    "iconId": 0,
    "plateId": 0,
    "codenameId": 0,
    "effectId": 0,
    "limitTimeSaleRemainSec": 0,
    "totMedalPoint": 0,
    "eventPointUpItemRemainSec": 0,
    "playerName": "",
    "todaysRemainSec": 0,
    "weeklyFreeFlg": 0,
    "hitodama": 0,
    "userId": "",
    "usingItemList": None,
    "hitodamaRecoverSec": 0,
    "limitTimeSaleEndDt": "",
    "equipWatchId": 0,
}


def _remaining_seconds_in_day() -> int:
    now = datetime.now()
    seconds_passed = now.hour * 3600 + now.minute * 60 + now.second
    return 86400 - seconds_passed


class YwpUserData:
    def __init__(self, icon_id: int | None = None, title_id: int | None = None,
                 player_name: str | None = None):
        d = dict(_FIELDS)
        d["usingItemList"] = []
        self.__dict__.update(d)
        if player_name is not None:
            self.youkaiId = 2235000
            self.playerName = player_name
            self.iconId = icon_id or 0
            self.titleId = title_id or 0
            self.freeHitodama = 5
            self.friendMaxCnt = 10
            self.nowStageId = 1001001
            self.ymoney = 3000
            self.hitodama = 0
            self.todaysRemainSec = _remaining_seconds_in_day()
            self.equipWatchId = 10101
            self.plateId = 1
            self.effectId = 1
            self.codenameId = 0

    @classmethod
    def from_dict(cls, d: dict) -> "YwpUserData":
        obj = cls()
        for key in _FIELDS:
            if key in d:
                setattr(obj, key, d[key])
        return obj

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in _FIELDS}

    @classmethod
    async def load(cls, gdkey: str) -> "YwpUserData | None":
        raw = await manage_data.get_ywp_user(gdkey, "ywp_user_data")
        if raw is None:
            return None
        obj = cls.from_dict(raw)
        await obj.hitodama_recover(gdkey)
        return obj

    @classmethod
    async def from_tables(cls, tables: dict, gdkey: str | None) -> "YwpUserData | None":
        raw = tables.get("ywp_user_data")
        if raw is None:
            return None
        obj = cls.from_dict(raw)
        if gdkey is not None:
            await obj.hitodama_recover(gdkey)
        return obj

    async def save(self, gdkey: str):
        await manage_data.set_ywp_user(gdkey, "ywp_user_data", self.to_dict())

    def buy_hitodama_good(self, price: int, sell_count: int, bonus_count: int):
        self.ymoney -= price
        self.hitodama += sell_count + bonus_count

    async def hitodama_recover(self, gdkey: str):
        now = datetime.now(timezone.utc)
        result = None
        try:
            t = await manage_data.get_ywp_user(gdkey, HITODAMA_RECOVER_TABLE)
            if isinstance(t, str):
                try:
                    result = datetime.strptime(t, TIME_FORMAT)
                except ValueError:
                    result = None
        except Exception:
            result = None
        if result is None:
            result = now
            await manage_data.set_ywp_user(
                gdkey, HITODAMA_RECOVER_TABLE, _fmt(result))

        seconds = int(result.timestamp())
        now_seconds = int(now.timestamp())
        diff = now_seconds - seconds
        current = self.hitodama + self.freeHitodama
        recovered = int(diff // HITODAMA_RECOVER_SEC)
        max_can_recover = FREE_HITODAMA_MAX - current
        applied = max(0, min(recovered, max_can_recover))
        self.freeHitodama += applied
        if current + applied >= FREE_HITODAMA_MAX:
            await manage_data.set_ywp_user(gdkey, HITODAMA_RECOVER_TABLE, _fmt(now))
            self.hitodamaRecoverSec = 0
        else:
            self.hitodamaRecoverSec = HITODAMA_RECOVER_SEC - (int(diff) % HITODAMA_RECOVER_SEC)
        if recovered != 0:
            if self.freeHitodama + self.hitodama < FREE_HITODAMA_MAX:
                now = now - timedelta(seconds=int(diff) % HITODAMA_RECOVER_SEC)
            await manage_data.set_ywp_user(gdkey, HITODAMA_RECOVER_TABLE, _fmt(now))
        await self.save(gdkey)


def _fmt(dt: datetime) -> str:
    s = dt.strftime(TIME_FORMAT)
    return s[:-2] + ":" + s[-2:]
