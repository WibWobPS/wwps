from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime

from . import config, game_data
from . import user_data as manage_data
from .dto import modi_dt
from .rows import (PuniMstStageItem, StageConditionItem, YwpMstConflate,
                   YwpMstGachaYoukaiChoice, YwpMstMission, YwpMstYoukai,
                   YwpMstYoukaiBonusEffect, YwpMstYoukaiLegendRelease,
                   YwpMstYoukaiLevel, YwpMstYoukaiLevelOpen, YwpMstYoukaiSkill,
                   YwpMstYoukaiSkillLevel, YwpUserMap, YwpUserMission,
                   YwpUserStage, YwpUserYoukai, YwpUserYoukaiBonusEffect,
                   YwpUserYoukaiSkill, parser_for, skill_level_get_befriender_pt)
from .table_parser import TableParser
from . import logging_setup, metrics

log = logging_setup.get(__name__)


class ConditionType:
    MinScore = 1; UsedYoukai = 2; MaxClearTime = 3; MaxPuniErase = 4
    FinishWithSpecificYoukaiSoult = 6; FinishWithSoult = 8; ClearStageNTimes = 9
    MinLinkSize = 10; MinSize = 11; MinCombo = 14; MinBonusBalls = 15
    MinFeverCount = 16; MaxMilisecondClearTime = 17; MinSuccess = 18
    CompleteStage = 19; ClearRankOnly = 20; ClearKindOnly = 21
    ClearWithoutContinue = 22; ClearWithoutHPRefill = 23; MinSMove = 24
    MinPuniErase = 25; MinHpRate = 27; MaxEnnemyAttackCount = 28
    MinDamageScoreWithKind = 29; ClearMaxRank = 30; MinSpecificYoukaiErase = 31
    MinSpecificYoukaiLink = 32; UseSpecificYoukaiSoult = 33
    MinSpecificYoukaiSize = 34; ClearWithOnlyFemalePuni = 35


class RarityType:
    RarityNone = 0; RarityE = 1; RarityD = 2; RarityC = 3; RarityB = 4
    RarityA = 5; RarityS = 6; RaritySS = 7; RaritySSS = 8; RarityZ = 9
    RarityZZ = 10; RarityZZZ = 11; RarityUZ = 12; RarityUZP = 13


class RewardType:
    NONE = 0; Icon = 12; YMoney = 3; Yokai = 2; Item = 1; Hitodama = 4
    Title = 13; IncreaseMaxFriends = 11; AddItemToShop = 10


class ItemType:
    MapWarpItem = 9; CrankCoin = 4; SoultBooster = 3; Exporb = 1; FuseItem = 5
    Watchpart = 7; Food = 2; BonusEffectBooster = 10


class SoultType:
    NONE = -1; Befriender = 11; SingleAttackerAndBefriender = 33


class MissionCompleteStatus:
    NotComplete = 0; CompleteRewardAcquired = 1; CompletePendingReward = 2


class MissionNewStatus:
    ShowNewPopup = 1; ShowNewTag = 2; NONE = 0


class MissionType:
    TotalScoreInScoreAttack = 70001; CollectTotalScore = 11002
    DoTotalSoults = 11003; CollectTotalStars = 21001; SendTotalSpirits = 51101
    FuseTotalYokai = 61001; PopTotalPuni = 11001; CreateTotalBonusBalls = 11004
    EnterFeverTimeTotalTimes = 11005; AddTotalYokaiToMedallium = 61401
    TotalLoginDays = 61301; CompleteStageInSeconds = 10103
    CollectStarsInMap = 21002; MinimumComboInStage = 10102
    GetSpecificYokaiToLevel = 40001; TotalPurchaseShop = 61201
    UseTotalItems = 31001; TotalCrank = 61101; DefeatBossWithTribe = 10105
    ClearStageWithRank = 10104; BuySpecificItemAtShop = 60201
    BefriendSpecificYokai = 40101; UseSpecificItemInBattle = 30001


class YokaiGetType:
    MaxLevel = 2; SoultLevelUp = 1; NewYokai = 10


class WatchStatus:
    Unlocked = 1; Locked = 10; LockedWithAllTheItems = 11


def exp_bar() -> dict:
    return {"pctg": 0, "denominator": 0, "numerator": 0}


def exp_info() -> dict:
    return {"level": 0, "exp": 0, "expBar": exp_bar()}


def skill_result() -> dict:
    return {"skillId": 0, "isMaxLevel": False, "before": exp_info(), "after": exp_info()}


def user_youkai_result_res(user_youkai=None, master_youkai=None) -> dict:
    res = {"haveFlg": False, "isMaxLevel": False, "isLockLevel": False,
           "before": exp_info(), "after": exp_info(), "youkaiId": 0,
           "canEvolve": False}
    if user_youkai is not None and master_youkai is not None:
        res["isMaxLevel"] = user_youkai.Level >= master_youkai.MaxLevel
        res["canEvolve"] = user_youkai.Level >= master_youkai.EvolutionLevel
        res["youkaiId"] = user_youkai.YoukaiId
        res["isLockLevel"] = user_youkai.IsLockedLevel == 1
    return res


def user_game_result_data() -> dict:
    return {"rewardYoukaiId": 0, "scoreUpdateFlg": 0, "score": 0,
            "isMaxItemFlg": 0, "money": 0, "prevRank": 0, "rank": 0,
            "starGetFlg3": 0, "starGetFlg2": 0, "starGetFlg1": 0,
            "prevScore": 0, "exp": 0, "stageId": 0}


class MasterStageData:
    _stage_items: list | None = None
    _condition_items: list | None = None

    @classmethod
    def stage_items(cls):
        if cls._stage_items is None:
            obj = json.loads(game_data.gamedata_cache["ywp_mst_stage"])
            built = []
            if obj.get("tableData") is not None:
                prsr = parser_for(PuniMstStageItem, obj["tableData"])
                for item in prsr.items:
                    built.append({
                        "StageId": item.StageId, "StageType": item.StageType,
                        "BattleType": 0,
                        "StarCondIDs": [item.StarCond1, item.StarCond2, item.StarCond3],
                        "BossFlag": item.BossFlag, "UseActionID": item.UseActionId,
                        "UseActionPoint": item.UseActionPoint,
                        "UseActionType": item.UseActionType})
            elif isinstance(obj.get("data"), list):
                for item in obj["data"]:
                    built.append({
                        "StageId": item["stageId"], "StageType": item["stageType"],
                        "BattleType": 0,
                        "StarCondIDs": [item["starGetConditionId1"],
                                        item["starGetConditionId2"],
                                        item["starGetConditionId3"]],
                        "BossFlag": item["bossFlg"], "UseActionID": item["useActionId"],
                        "UseActionPoint": item["useActionPoint"],
                        "UseActionType": item["useActionType"]})
            else:
                raise ValueError("Bad ywp_mst_stage")
            cls._stage_items = built
        return cls._stage_items

    @classmethod
    def condition_items(cls):
        if cls._condition_items is None:
            obj = json.loads(game_data.gamedata_cache["ywp_mst_stage_condition"])
            if obj.get("tableData") is not None:
                prsr = parser_for(StageConditionItem, obj["tableData"], delimiter="^")
                cls._condition_items = prsr.items
            elif isinstance(obj.get("data"), list):
                items = []
                for d in obj["data"]:
                    it = StageConditionItem(
                        ConditionId=d.get("conditionId", 0),
                        ConditionType=d.get("conditionType", 0),
                        Description=d.get("description", ""),
                        ConditionVal1=d.get("conditionVal1", 0),
                        ConditionVal2=d.get("conditionVal2", 0),
                        ConditionVal3=d.get("conditionVal3", 0))
                    it.OpenStageIdList = d.get("openStageIdList", "")
                    items.append(it)
                cls._condition_items = items
            else:
                raise ValueError("Bad ywp_mst_stage_condition")
        return cls._condition_items

    @classmethod
    def get_stage_condition_index(cls, condition_id) -> int:
        for i, it in enumerate(cls.condition_items()):
            if it.ConditionId == condition_id:
                return i
        return -1

    @classmethod
    def get_next_stage(cls, stage_id: int) -> int:
        items = cls.stage_items()
        map_id = int(math.floor(stage_id / 1000.0))
        count = (int(stage_id) % 1000) + 1
        while True:
            idx = next((i for i, x in enumerate(items)
                        if x["StageId"] == map_id * 1000 + count), -1)
            if idx == -1:
                break
            if items[idx]["StageType"] == 1:
                return items[idx]["StageId"]
            count += 1
        return -1

    @classmethod
    def get_unlocked_secret_stage(cls, stage_id: int, _skipp: int) -> int:
        items = cls.stage_items()
        map_id = int(math.floor(stage_id / 1000.0))
        max_stage_id = int(stage_id) % 1000
        skipp = 0
        count = 1
        while True:
            idx = next((i for i, x in enumerate(items)
                        if x["StageId"] == map_id * 1000 + count), -1)
            if idx == -1:
                break
            if count < max_stage_id:
                _count = 4
                while True:
                    cond_idx = cls.get_stage_condition_index(
                        ((map_id * 1000 + count) * 10) + _count)
                    if cond_idx == -1:
                        break
                    skipp += 1
                    _count += 1
            else:
                if items[idx]["StageType"] == 2:
                    if skipp > 0:
                        skipp -= 1
                    elif _skipp > 0:
                        _skipp -= 1
                    else:
                        return items[idx]["StageId"]
            count += 1
        return -1


def _is_finish_with_soult(enemies: list[dict], youkai_id: int = -1) -> bool:
    biggest = 0
    for item in enemies:
        if item.get("deadEndOrder", 0) > biggest:
            biggest = item.get("deadEndOrder", 0)
    last = next((x for x in enemies if x.get("deadEndOrder", 0) == biggest), None)
    if last is None:
        return False
    if youkai_id == -1 and last.get("deadEndType", 0) != 0:
        return True
    if last.get("deadEndType", 0) == youkai_id:
        return True
    return False


def compute_stage_condition(ctype: int, req: dict, stage_item, p1: int, p2: int, p3: int) -> bool:
    if ctype == ConditionType.MinScore and req.get("score", 0) >= p1:
        return True
    if ctype == ConditionType.UsedYoukai:
        for item in req.get("userYoukaiResultList") or []:
            if item.get("youkaiId") == p1:
                return True
        return False
    if ctype == ConditionType.MaxClearTime and req.get("clearTimeSec", 0) <= p1:
        return True
    if ctype == ConditionType.MaxPuniErase and req.get("eraseNumTotal", 0) <= p1:
        return True
    if ctype == ConditionType.FinishWithSpecificYoukaiSoult:
        return _is_finish_with_soult(req.get("enemyYoukaiResultList") or [], p1)
    if ctype == ConditionType.FinishWithSoult:
        return _is_finish_with_soult(req.get("enemyYoukaiResultList") or [], -1)
    if ctype == ConditionType.ClearStageNTimes and stage_item.NumClear >= p1:
        return True
    if ctype == ConditionType.MinLinkSize and req.get("linkSizeMax", 0) >= p1:
        return True
    if ctype == ConditionType.MinSize and req.get("eraseSizeMax", 0) >= p1:
        return True
    if ctype == ConditionType.MinCombo and req.get("comboMax", 0) >= p1:
        return True
    if ctype == ConditionType.MinBonusBalls and req.get("bonusBlockNum", 0) >= p1:
        return True
    if ctype == ConditionType.MinFeverCount and req.get("feverTimeNum", 0) >= p1:
        return True
    if ctype == ConditionType.MaxMilisecondClearTime and req.get("clearTimeSec", 0) * 1000 >= p1:
        return True
    if ctype == ConditionType.CompleteStage:
        return True
    if ctype == ConditionType.MinPuniErase and req.get("eraseNumTotal", 0) >= p1:
        return True
    if ctype == ConditionType.MaxEnnemyAttackCount and req.get("resultRecvAtkNum", 0) <= p1:
        return True
    if ctype == ConditionType.UseSpecificYoukaiSoult:
        for kai in req.get("userYoukaiResultList") or []:
            if kai.get("youkaiId") == p1 and kai.get("skillUseNum", 0) > 0:
                return True
        return False
    return False


def get_table_index(parser: TableParser, data: list[tuple[int, str]]) -> int:
    index = 0
    good = True
    for item in parser.table:
        good = True
        for col, val in data:
            if item[col] != val:
                good = False
        if good:
            break
        index += 1
    if not good:
        return -1
    return index


def get_table_indexes(parser: TableParser, data: list[tuple[int, str]]) -> list[int]:
    out = []
    for index, item in enumerate(parser.table):
        good = True
        for col, val in data:
            if item[col] != val:
                good = False
        if good:
            out.append(index)
    return out


def edit_dictionary_raw(parser: TableParser, youkai_id: int, add_seen: bool,
                        add_befriends: bool) -> TableParser:
    idx = parser.find_index([str(youkai_id)])
    seen = 1 if add_seen else 0
    befriend = 1 if add_befriends else 0
    if idx == -1:
        parser.add_row([str(youkai_id), str(befriend), str(seen)])
    else:
        if add_seen:
            parser.table[idx][2] = "1"
        if add_befriends:
            parser.table[idx][1] = "1"
    return TableParser(str(parser))


def get_dictionary_index(parser, youkai_id: int) -> int:
    for i, it in enumerate(parser.items):
        if it.YoukaiId == youkai_id:
            return i
    return -1


def edit_dictionary(parser, youkai_id: int, add_seen: bool, add_befriends: bool):
    from .rows import YwpUserDictionary
    idx = get_dictionary_index(parser, youkai_id)
    if idx == -1:
        parser.add_item(YwpUserDictionary(
            YoukaiId=youkai_id, IsBefriend=1 if add_befriends else 0,
            IsSeen=1 if add_seen else 0))
        return
    if add_seen:
        parser.items[idx].IsSeen = 1
    if add_befriends:
        parser.items[idx].IsBefriend = 1


def add_icon(parser: TableParser, icon_id: int) -> TableParser:
    found = any(int(row[0]) == icon_id for row in parser.table)
    if not found:
        parser.add_row([str(icon_id)])
    return TableParser(str(parser))


def item_add(parser, item_id: int, item_count: int):
    from .rows import YwpUserItem
    item = next((x for x in parser.items if x.ItemId == item_id), None)
    if item is not None:
        item.Count += item_count
    else:
        parser.items.append(YwpUserItem(ItemId=item_id, Count=item_count))
    return parser


def item_remove(parser, item_id: int, item_count: int):
    item = next(x for x in parser.items if x.ItemId == item_id)
    if item.Count > item_count:
        item.Count -= item_count
    else:
        parser.items.remove(item)
    return parser


def map_get_index(parser, map_id: int) -> int:
    for i, it in enumerate(parser.items):
        if it.MapId == map_id:
            return i
    return -1


def map_add(parser, map_id: int):
    if map_get_index(parser, map_id) == -1:
        parser.add_item(YwpUserMap(MapId=map_id, IsUnlocked=0, FriendCount=0))


def map_update(parser, map_id: int, is_unlocked: int):
    idx = map_get_index(parser, map_id)
    if idx != -1:
        if is_unlocked == 1 and parser.items[idx].IsUnlocked == 0:
            parser.items[idx].IsUnlocked = 1


def menufunc_search(parser, app_id: int) -> int:
    for i, it in enumerate(parser.items):
        if it.AppId == app_id:
            return i
    return -1


def menufunc_add(parser, app_id: int, flg: int):
    from .rows import YwpUserMenufunc
    idx = menufunc_search(parser, app_id)
    if idx == -1:
        parser.items.append(YwpUserMenufunc(AppId=app_id, AppFlg=flg))
        return parser
    if flg == 1:
        parser.items[idx].AppFlg = flg
    return parser


def stage_get_index(parser, stage_id: int) -> int:
    for i, it in enumerate(parser.items):
        if it.StageId == stage_id:
            return i
    return -1


def stage_add(parser, stage_id: int):
    user_idx = stage_get_index(parser, stage_id)
    mst_idx = next((i for i, x in enumerate(MasterStageData.stage_items())
                    if x["StageId"] == stage_id), -1)
    if user_idx == -1 and mst_idx != -1:
        parser.add_item(YwpUserStage(StageId=stage_id))


def stage_edit(parser, stage_id: int, is_clear: int, score: int,
               star1: int, star2: int, star3: int, num_clear: int):
    user_idx = stage_get_index(parser, stage_id)
    mst_idx = next((i for i, x in enumerate(MasterStageData.stage_items())
                    if x["StageId"] == stage_id), -1)
    if user_idx == -1 or mst_idx == -1:
        return
    it = parser.items[user_idx]
    if score > it.Score:
        it.Score = score
    if is_clear == 1 and it.StageStatus == 0:
        it.StageStatus = 1
    if star1 == 1 and it.Star1 == 0:
        it.Star1 = 1
    if star2 == 1 and it.Star2 == 0:
        it.Star2 = 1
    if star3 == 1 and it.Star3 == 0:
        it.Star3 = 1
    if num_clear > it.NumClear:
        it.NumClear = num_clear


_gacha_choice_table = None


def gacha_choice_is_ok(gacha_id: int, youkai_id: int) -> bool:
    global _gacha_choice_table
    if _gacha_choice_table is None:
        _gacha_choice_table = parser_for(
            YwpMstGachaYoukaiChoice,
            game_data.get_table_string_from_json("ywp_mst_gacha_youkai_choice"))
    return any(x.GachaID == gacha_id and x.YokaiID == youkai_id
               for x in _gacha_choice_table.items)


_skill_level_entries = None
_skill_level_cache: dict = {}


def mst_skill_level_get_entry(youkai_id: int, soult_level: int):
    global _skill_level_entries
    if _skill_level_entries is None:
        _skill_level_entries = parser_for(
            YwpMstYoukaiSkillLevel,
            game_data.get_table_string_from_json("ywp_mst_youkai_skill_level")).items
    key = (youkai_id, soult_level)
    if key in _skill_level_cache:
        return _skill_level_cache[key]
    entry = next((x for x in _skill_level_entries
                  if x.YoukaiID == youkai_id and x.SoultLevel == soult_level), None)
    if entry is None:
        raise KeyError("Can't find soult data for befriender")
    _skill_level_cache[key] = entry
    return entry


_mst_skill_table = None


def mst_skill_get_obj(youkai_id: int):
    global _mst_skill_table
    if _mst_skill_table is None:
        raw = json.loads(game_data.gamedata_cache["ywp_mst_youkai_skill"])["tableData"]
        _mst_skill_table = parser_for(YwpMstYoukaiSkill, raw)
    return next((x for x in _mst_skill_table.items if x.SoultID == youkai_id), None)


def mst_skill_is_befriender(obj) -> bool:
    return obj.SoultType in (SoultType.Befriender, SoultType.SingleAttackerAndBefriender)


_mst_bonus_effect_table = None


def mst_is_have_bonus_effect(youkai_id: int) -> bool:
    global _mst_bonus_effect_table
    if _mst_bonus_effect_table is None:
        _mst_bonus_effect_table = parser_for(
            YwpMstYoukaiBonusEffect,
            game_data.get_table_string_from_json("ywp_mst_youkai_bonus_effect"))
    return any(x.YoukaiID == youkai_id for x in _mst_bonus_effect_table.items)


_mst_legend_release_table = None


def mst_legend_release_table():
    global _mst_legend_release_table
    if _mst_legend_release_table is None:
        raw = json.loads(game_data.gamedata_cache["ywp_mst_youkai_legend_release"])["tableData"]
        _mst_legend_release_table = parser_for(YwpMstYoukaiLegendRelease, raw)
    return _mst_legend_release_table


def check_legend_youkai_id(youkai_id: int) -> int:
    tbl = mst_legend_release_table()
    for it in tbl.items:
        if youkai_id in (it.Yokai1ID, it.Yokai2ID, it.Yokai3ID,
                         it.Yokai4ID, it.Yokai5ID, it.Yokai6ID):
            return it.LegendYokaiID
    return 0


_shop_hitodama_data = None


def shop_hitodama_data() -> list[dict]:
    global _shop_hitodama_data
    if _shop_hitodama_data is None:
        _shop_hitodama_data = json.loads(
            game_data.gamedata_cache["ywp_mst_shop_hitodama_list"])["data"]
    return _shop_hitodama_data


def mst_map_get_index(maps: list[dict], map_id: int) -> int:
    for i, m in enumerate(maps):
        if m.get("mapId") == map_id:
            return i
    return -1


def mst_youkai_get_index(parser, youkai_id: int) -> int:
    for i, it in enumerate(parser.items):
        if it.YoukaiId == youkai_id:
            return i
    return -1


def mst_youkai_level_index(parser, level_type: int, level: int) -> int:
    for i, it in enumerate(parser.items):
        if it.LevelTtype == level_type and it.Level == level:
            return i
    return -1


def mst_youkai_level_open_index(parser, before_level: int, after_level: int,
                                rarity_type: int) -> int:
    res = -1
    currlevel = 0
    for i, it in enumerate(parser.items):
        if (it.RarityType == rarity_type and before_level < it.Level
                and after_level >= it.Level and (it.Level < currlevel or currlevel == 0)):
            currlevel = it.Level
            res = i
    return res


async def check_shop_limit_reset(gdkey: str):
    today = datetime.utcnow().strftime("%Y%m%d")
    last = await manage_data.get_ywp_user(gdkey, "lastShopResetDate")
    if last != today:
        await manage_data.set_ywp_user(gdkey, "ywp_user_shop_item_remain_cnt", "")
        await manage_data.set_ywp_user(gdkey, "lastShopResetDate", today)


def _get_is_befriender(youkai_id: int, user_skill) -> tuple[int, int]:
    skill_obj = mst_skill_get_obj(youkai_id)
    if skill_obj is None:
        return (youkai_id, 0)
    if mst_skill_is_befriender(skill_obj):
        idx = next((i for i, x in enumerate(user_skill.items)
                    if x.YoukaiId == youkai_id), -1)
        if idx == -1:
            raise Exception("Weird issue bad skill shouldnt happen")
        return (youkai_id, user_skill.items[idx].Level)
    return (youkai_id, 0)


def get_befriender_spots(deck, user_skill) -> list[tuple[int, int]]:
    d = deck.items[0]
    return [
        _get_is_befriender(d.MiddleYoukaiId, user_skill),
        _get_is_befriender(d.MiddleLeftYoukaiId, user_skill),
        _get_is_befriender(d.MiddleRightYoukaiId, user_skill),
        _get_is_befriender(d.FarLeftYoukaiId, user_skill),
        _get_is_befriender(d.FarRightYoukaiId, user_skill),
    ]


BASE_RATE_BY_RANK = {
    RarityType.RarityE: 0.11, RarityType.RarityD: 0.10, RarityType.RarityC: 0.08,
    RarityType.RarityB: 0.06, RarityType.RarityA: 0.01, RarityType.RarityS: 0.01,
    RarityType.RaritySS: 0.03,
}
_FOOD_MULTIPLIERS = [1.00, 1.50, 1.75, 2.00, 4.25]
_SUPER_SHRINE_MULTIPLIER = _FOOD_MULTIPLIERS[3]


def _get_soultimate_boost(pattern: str, pts_arr: list[float]) -> float:
    total = 1.0
    weights = [0.6, 0.3, 0.1]
    for i, ch in enumerate(pattern):
        use_count = ord(ch) - ord('0')
        percent = 0.0
        for j in range(use_count):
            weight = weights[j] if j < len(weights) else 0
            percent += pts_arr[i] * weight
        total *= 1 + percent / 100
    return total


def _get_befriend_weight(enemy_rank: int, bit_pos: int, boost: float,
                         is_super_shrine: bool) -> float:
    base = BASE_RATE_BY_RANK[enemy_rank]
    food = _FOOD_MULTIPLIERS[bit_pos]
    shrine = _SUPER_SHRINE_MULTIPLIER if is_super_shrine else 0.0
    pre = base * boost * max(shrine, food)
    return min(max(pre, 0.0), 1.0)


def _generate_lot_result(enemy_rank: int, boost: float, is_super_shrine: bool,
                         autobefriend: bool) -> str:
    if autobefriend:
        return "11111"
    return "".join(
        '1' if random.random() < _get_befriend_weight(enemy_rank, b, boost, is_super_shrine)
        else '0' for b in range(5))


def _generate_lot_patterns(befrienders: list[tuple[int, int]]) -> list[str]:
    active = [i for i, b in enumerate(befrienders) if b[1] != 0]
    patterns: list[str] = []
    chars = ['0'] * len(befrienders)

    def recurse(depth: int):
        if depth == len(active):
            patterns.append("".join(chars))
            return
        index = active[depth]
        for c in "0123":
            chars[index] = c
            recurse(depth + 1)
        chars[index] = '0'

    recurse(0)
    return patterns


def _get_befriender_pts(befrienders: list[tuple[int, int]]) -> list[float]:
    PT_DIVISOR = 187.5
    pts = []
    for yid, lvl in befrienders:
        if lvl != 0:
            pts.append(skill_level_get_befriender_pt(
                mst_skill_level_get_entry(yid, lvl)) / PT_DIVISOR)
        else:
            pts.append(0.0)
    return pts


def generate_lot_youkai(befrienders, enemy_rank: int, is_super_shrine: bool,
                        autobefriend: bool) -> list[dict]:
    pts_arr = _get_befriender_pts(befrienders)
    patterns = _generate_lot_patterns(befrienders)
    entries = []
    for pattern in patterns:
        boost = _get_soultimate_boost(pattern, pts_arr)
        entries.append({
            "lotPattern": pattern,
            "lotResult": _generate_lot_result(enemy_rank, boost, is_super_shrine,
                                              autobefriend)})
    return entries


_rare_enemies = None


def rare_enemy_get_drop(stage_id: int) -> int:
    global _rare_enemies
    if _rare_enemies is None:
        _rare_enemies = json.loads(game_data.gamedata_cache["rare_enemy"])
    mst = next((x for x in MasterStageData.stage_items()
                if x["StageId"] == stage_id), None)
    if mst is None:
        return -1
    if mst["BossFlag"] == 0:
        stage_entries = [x for x in _rare_enemies
                         if x.get("Scope") == 1 and stage_id in (x.get("Params") or [])]
        for entry in stage_entries:
            if random.randrange(100) < entry["Rate"]:
                return entry["EnemyID"]
        map_id = stage_id // 1000
        map_entry = next(
            (x for x in _rare_enemies
             if x.get("Scope") == 0 and map_id in (x.get("Params") or [])
             and (not x.get("ExceptionParams") or stage_id not in x["ExceptionParams"])),
            None)
        if map_entry is not None and random.randrange(100) < map_entry["Rate"]:
            return map_entry["EnemyID"]
    return -1


def create_present(recv_user_id, all_receive: bool, bonus: bool, userdata,
                   reward_id: int, reward_type: int, item_cnt: int,
                   body_text: str) -> dict:
    present = {
        "bonusLimitMsg": "", "distItemResource": "", "msgType": 0,
        "targetIconId": 0, "canReceiveAll": 1 if all_receive else 0,
        "limitDtStr": None, "distItemCnt": item_cnt, "targetTitleId": 0,
        "targetUserId": None, "distItemId": reward_id, "userId": None,
        "distItemType": 0, "bodyText": body_text, "bonusYmoney": 0,
        "targetPlayerName": None, "iconType": 0, "layerName": "",
        "distItemName": "", "seq": int(random.random() * 1_000_000_000_000),
        "regDtStr": None,
    }
    if bonus:
        present["bonusLimitMsg"] = "1 jour"
        present["bonusYmoney"] = 10
    if recv_user_id is None:
        present["msgType"] = 200
        present["targetTitleId"] = 0
        present["targetIconId"] = 0
        present["targetUserId"] = ""
        present["targetPlayerName"] = ""
        present["iconType"] = 2
        present["userId"] = userdata.userId
    else:
        present["userId"] = recv_user_id
        present["targetUserId"] = userdata.userId
        present["iconType"] = 1
        present["msgType"] = 10 if all_receive else 60
    return present


def get_time_difference_string(string_date: str) -> str:
    given = datetime.strptime(string_date, "%Y-%m-%d %H:%M:%S")
    diff = datetime.now() - given
    total_minutes = diff.total_seconds() / 60
    if total_minutes < 60:
        return f"+{int(total_minutes)} mins"
    if total_minutes < 24 * 60:
        return f"+{int(total_minutes // 60)} hrs"
    days = int(diff.days)
    if days > 10:
        days = 10
    return f"+{days} days"


async def refresh_ywp_user_friend(gdkey: str, title_id: int, icon_id: int,
                                  player_name: str, youkai_id: int,
                                  last_play_dt: str):
    from .ywp_user_data import YwpUserData
    me = await YwpUserData.load(gdkey)
    my_friend_list = await manage_data.get_ywp_user(gdkey, "ywp_user_friend") or []
    for item in my_friend_list:
        target_gdkey = await manage_data.get_gdkey_from_user_id(item.get("userId") or "")
        if not target_gdkey:
            continue
        friend_list = await manage_data.get_ywp_user(target_gdkey, "ywp_user_friend") or []
        for item2 in friend_list:
            if item2.get("userId") == me.userId:
                if title_id > 0:
                    item2["titleId"] = title_id
                if icon_id > 0:
                    item2["iconId"] = icon_id
                if player_name:
                    item2["playerName"] = player_name
                if youkai_id > 0:
                    item2["youkaiId"] = youkai_id
                if last_play_dt:
                    item2["lastPlayDt"] = last_play_dt
        await manage_data.set_ywp_user(target_gdkey, "ywp_user_friend", friend_list)


async def refresh_ywp_user_friend_rank(gdkey: str, add_stars: int, mode: int):
    from .ywp_user_data import YwpUserData

    def edit_element(element: dict, stars: int, userdata):
        element["titleId"] = userdata.titleId
        element["playerName"] = userdata.playerName
        element["iconId"] = userdata.iconId
        if stars > 0:
            element["getStarModiDt"] = modi_dt()
            element["getStar"] = element.get("getStar", 0) + stars

    me = await YwpUserData.load(gdkey)
    if mode == 0:
        table = "ywp_user_friend_star_rank"
    elif mode == 1:
        table = "ywp_user_friend_rank"
    else:
        raise Exception()
    my_rank_list = await manage_data.get_ywp_user(gdkey, table) or []
    for item in my_rank_list:
        if item.get("self") == 1:
            edit_element(item, add_stars, me)
            await manage_data.set_ywp_user(gdkey, table, my_rank_list)
            continue
        target_gdkey = await manage_data.get_gdkey_from_user_id(item.get("userId") or "")
        if not target_gdkey:
            continue
        friend_rank_list = await manage_data.get_ywp_user(target_gdkey, "ywp_user_friend") or []
        for item2 in friend_rank_list:
            if item2.get("userId") == me.userId:
                edit_element(item2, add_stars, me)
        await manage_data.set_ywp_user(target_gdkey, table, friend_rank_list)


_SOUL_LEVEL_COSTS = [0, 1000, 2000, 4000, 6000, 9000, 12000]


def _soul_level_formula(n: int) -> int:
    if n < 0 or n >= len(_SOUL_LEVEL_COSTS):
        return 0
    return _SOUL_LEVEL_COSTS[n]


def _soul_level(n: int) -> int:
    points = 0
    for i in range(1, 7):
        points += _soul_level_formula(i)
        if n < points:
            return i
    return 7


def _soul_points(n: int) -> int:
    return sum(_soul_level_formula(i) for i in range(1, n + 1))


def get_youkai_skill_index(parser, youkai_id: int) -> int:
    return next((i for i, x in enumerate(parser.items)
                 if x.YoukaiId == youkai_id), -1)


def get_youkai_index(parser, youkai_id: int) -> int:
    return next((i for i, x in enumerate(parser.items)
                 if x.YoukaiId == youkai_id), -1)


def add_exp_to_skill(youkai_list, youkai_id: int, exp_to_add: int) -> dict | None:
    idx = get_youkai_skill_index(youkai_list, youkai_id)
    if idx == -1:
        return None
    it = youkai_list.items[idx]
    amu_level = it.Level
    res = skill_result()
    res["skillId"] = youkai_id
    res["before"]["level"] = amu_level
    res["before"]["exp"] = it.Points
    res["before"]["expBar"]["denominator"] = it.PercentageDenominator
    res["before"]["expBar"]["numerator"] = it.PercentageNumerator
    res["before"]["expBar"]["pctg"] = it.Percentage
    if amu_level >= 7:
        res["after"] = json.loads(json.dumps(res["before"]))
        res["isMaxLevel"] = True
        return res
    current = res["before"]["exp"]
    new_points = exp_to_add + current
    res["after"]["exp"] = new_points
    new_level = _soul_level(new_points)
    denominator = _soul_level_formula(new_level)
    numerator = new_points - _soul_points(new_level - 1)
    percentage = int((numerator / denominator) * 100)
    if new_level >= 7:
        percentage = 0
    res["after"]["level"] = new_level
    res["after"]["expBar"]["denominator"] = denominator
    res["after"]["expBar"]["numerator"] = numerator
    res["after"]["expBar"]["pctg"] = percentage
    return res


def delete_youkai(user_yokai, user_skill, youkai_id: int, bonus):
    yokai_idx = get_youkai_index(user_yokai, youkai_id)
    if yokai_idx == -1:
        raise NotImplementedError("Yokai not found in user")
    skill_idx = get_youkai_skill_index(user_skill, youkai_id)
    if skill_idx == -1:
        raise NotImplementedError("Skill not found in user")
    bonus_idx = next((i for i, x in enumerate(bonus.items)
                      if x.YoukaiID == youkai_id), -1)
    if bonus_idx != -1:
        del bonus.items[bonus_idx]
    del user_yokai.items[yokai_idx]
    del user_skill.items[skill_idx]


def _add_youkai_bonus_eff(bonus_eff, youkai_id: int):
    if mst_is_have_bonus_effect(youkai_id) and \
            not any(x.YoukaiID == youkai_id for x in bonus_eff.items):
        bonus_eff.items.append(YwpUserYoukaiBonusEffect(
            YoukaiID=youkai_id, BonusEffectLevel=1,
            BonusEff2ActivatedFlg=0, BonusEff3ActivatedFlg=0))


def _add_youkai_skill(youkai_list, youkai_id: int):
    idx = get_youkai_skill_index(youkai_list, youkai_id)
    if idx == -1:
        youkai_list.add_item(YwpUserYoukaiSkill(
            YoukaiId=youkai_id, Level=1, Points=0, PercentageDenominator=1000,
            PercentageNumerator=0, Percentage=0))
        return
    it = youkai_list.items[idx]
    if it.Level >= 7:
        return
    new_points = 1000 + it.Points
    new_level = _soul_level(new_points)
    denominator = _soul_level_formula(new_level)
    numerator = new_points - _soul_points(new_level - 1)
    percentage = int((numerator / denominator) * 100)
    if new_level >= 7:
        percentage = 0
    it.Level = new_level
    it.Points = new_points
    it.PercentageDenominator = denominator
    it.PercentageNumerator = numerator
    it.Percentage = percentage


async def add_youkai(user_yokai, youkai_id: int, user_skill, user_bonus,
                     gdkey: str, user_mission=None, manual_mission_save=False):
    youkai_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_youkai"])["tableData"])
    youkai_level_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_youkai_level"])["tableData"])
    user_idx = get_youkai_index(user_yokai, youkai_id)
    mst_idx = next((i for i, x in enumerate(youkai_mst.table)
                    if x[0] == str(youkai_id)), -1)
    if user_idx == -1:
        um = await mission_update_progress(
            gdkey, MissionType.AddTotalYokaiToMedallium, 1, user_mission,
            manual_mission_save)
        await mission_update_progress(
            gdkey, MissionType.BefriendSpecificYokai, int(youkai_id), um,
            manual_mission_save)
        await mission_update_progress(
            gdkey, MissionType.GetSpecificYokaiToLevel, int(youkai_id),
            param_user_mission=um, manual_save=manual_mission_save,
            progress_to_update2=1)
        tmp_idx = 0
        level_type = int(youkai_mst.table[mst_idx][5])
        for row in youkai_level_mst.table:
            if row[0] == str(level_type) and row[1] == "1":
                break
            tmp_idx += 1
        user_yokai.add_item(YwpUserYoukai(
            YoukaiId=youkai_id, Level=1, Exp=0,
            Hp=int(youkai_mst.table[mst_idx][8]),
            Atk=int(youkai_mst.table[mst_idx][10]),
            ExpDenominator=int(youkai_level_mst.table[tmp_idx][3]),
            ExpNumerator=0, Percentage=0,
            IsLockedLevel=0,
            BefriendDate=int(time.time() * 1000), BreakLimitCount=0))
    _add_youkai_skill(user_skill, youkai_id)
    _add_youkai_bonus_eff(user_bonus, youkai_id)


MAX_SOULT = 7


def check_get_type(yokai_id: int, user_yokai, user_skill) -> int:
    yokai_idx = get_youkai_index(user_yokai, yokai_id)
    if yokai_idx == -1:
        return YokaiGetType.NewYokai
    soult_idx = get_youkai_skill_index(user_skill, yokai_id)
    if soult_idx == -1:
        raise Exception("No soult idx found for yokai")
    if user_skill.items[soult_idx].Level == MAX_SOULT:
        return YokaiGetType.MaxLevel
    return YokaiGetType.SoultLevelUp


def yokai_won_popup(yokai_id: int, user_yokai, user_skill) -> dict:
    popup = {
        "bonusEffectLevelAfter": 0, "strongSkillLevelBefore": 0,
        "bonusEffectLevelBefore": 0,
        "legendYoukaiId": check_legend_youkai_id(yokai_id),
        "strongSkillLevelAfter": 0, "isWBonusEffectOpen": False,
        "levelAfter": 0, "levelBefore": 0, "getType": 0,
        "youkaiId": yokai_id, "releaseType": 0, "skill": None,
        "exchgYmoney": 0, "exp": 0, "limitLevelBefore": 0,
        "limitLevelAfter": 0, "releaseLevelType": 0,
    }
    popup["getType"] = check_get_type(yokai_id, user_yokai, user_skill)
    if popup["getType"] == YokaiGetType.SoultLevelUp:
        popup["skill"] = add_exp_to_skill(user_skill, yokai_id, 1000)
    return popup


_NOT_CARRY_OVER = {MissionType.BuySpecificItemAtShop,
                   MissionType.UseSpecificItemInBattle,
                   MissionType.BefriendSpecificYokai,
                   MissionType.GetSpecificYokaiToLevel}

_BASIC_PROGRESS = {MissionType.CollectTotalScore, MissionType.CollectTotalStars,
                   MissionType.TotalCrank, MissionType.TotalLoginDays,
                   MissionType.UseTotalItems, MissionType.AddTotalYokaiToMedallium,
                   MissionType.FuseTotalYokai, MissionType.TotalPurchaseShop,
                   MissionType.TotalScoreInScoreAttack,
                   MissionType.CreateTotalBonusBalls, MissionType.DoTotalSoults,
                   MissionType.PopTotalPuni, MissionType.EnterFeverTimeTotalTimes}

_BASIC_PARAM = {MissionType.BefriendSpecificYokai,
                MissionType.BuySpecificItemAtShop,
                MissionType.UseSpecificItemInBattle}

_mst_mission = None
_series_cfg = None


def _get_series_cfg() -> list[dict]:
    global _series_cfg
    if _series_cfg is None:
        _series_cfg = json.loads(game_data.gamedata_cache["mission_cfg"])
    return _series_cfg


def get_mst_mission():
    global _mst_mission
    if _mst_mission is None:
        raw = json.loads(game_data.gamedata_cache["ywp_mst_mission"])
        _mst_mission = parser_for(YwpMstMission, raw["tableData"])
    return _mst_mission


async def get_user_mission(gdkey: str):
    raw = await manage_data.get_ywp_user(gdkey, "ywp_user_mission")
    return parser_for(YwpUserMission, raw if isinstance(raw, str) else None)


def sort_user_mission(user_mission, finished_missions_is_appear: int,
                      kill_new_popup: bool):
    for mission in user_mission.items:
        if mission.MissionCompleteStatus == MissionCompleteStatus.CompleteRewardAcquired:
            mission.IsAppear = finished_missions_is_appear
        if mission.NewStatus in (MissionNewStatus.ShowNewPopup,
                                 MissionNewStatus.ShowNewTag) and kill_new_popup:
            mission.NewStatus = MissionNewStatus.NONE
    new_order = []
    new_order += [x for x in user_mission.items
                  if x.MissionCompleteStatus == MissionCompleteStatus.CompletePendingReward]
    new_order += [x for x in user_mission.items
                  if x.MissionCompleteStatus == MissionCompleteStatus.NotComplete]
    new_order += sorted(
        (x for x in user_mission.items
         if x.MissionCompleteStatus == MissionCompleteStatus.CompleteRewardAcquired),
        key=lambda x: x.MissionID)
    user_mission.items = new_order


async def save_user_mission(gdkey: str, user_mission):
    await manage_data.set_ywp_user(gdkey, "ywp_user_mission", str(user_mission))


def _get_mission_cfg_idx(mission_id: int):
    for series in _get_series_cfg():
        for i, m in enumerate(series["Missions"]):
            if m["MissionID"] == mission_id:
                return series, i
    return None, -1


async def try_unlock_next_mission(mission_id: int, user_mission, user_yokai):
    current_idx = next((i for i, x in enumerate(user_mission.items)
                        if x.MissionID == mission_id), -1)
    current = user_mission.items[current_idx]
    current.IsAppear = 0
    user_mission.items.remove(current)
    user_mission.items.append(current)
    series, cfg_idx = _get_mission_cfg_idx(mission_id)
    next_idx = cfg_idx + 1
    if series is not None and len(series["Missions"]) > next_idx:
        nxt = series["Missions"][next_idx]
        new_progress = current.MissionParamProgress
        new_target = nxt["Params"][0]
        if nxt["MissionType"] in _NOT_CARRY_OVER:
            new_progress = 0
        if nxt["MissionType"] == MissionType.GetSpecificYokaiToLevel:
            yokai_id = nxt["Params"][0]
            my_yokai = next((x for x in user_yokai.items
                             if x.YoukaiId == yokai_id), None)
            if my_yokai is not None:
                new_progress = my_yokai.Level
            new_target = nxt["Params"][1]
        new_mission = YwpUserMission(
            MissionID=nxt["MissionID"],
            SeqNo=int("1" + str(nxt["MissionID"])),
            MissionCompleteStatus=MissionCompleteStatus.NotComplete,
            IsAppear=1,
            MissionParamTarget=new_target,
            MissionParamProgress=new_progress,
            NewStatus=MissionNewStatus.ShowNewPopup)
        if new_progress >= new_mission.MissionParamTarget:
            new_mission.MissionCompleteStatus = MissionCompleteStatus.CompletePendingReward
        user_mission.items.insert(current_idx, new_mission)


def _basic_progress_check(mission, progress: int):
    mission.MissionParamProgress += progress
    if mission.MissionParamProgress >= mission.MissionParamTarget:
        mission.MissionCompleteStatus = MissionCompleteStatus.CompletePendingReward


def _basic_param_check(mission, progress: int, param: int):
    if param == progress:
        mission.MissionParamProgress = 1
        mission.MissionCompleteStatus = MissionCompleteStatus.CompletePendingReward


async def mission_update_progress(gdkey: str, mission_type: int,
                                  progress_to_update: int,
                                  param_user_mission=None, manual_save=False,
                                  progress_to_update2: int = -1,
                                  replace_value: bool = False):
    if param_user_mission is None:
        user_mission = await get_user_mission(gdkey)
    else:
        user_mission = param_user_mission
    mst_mission = get_mst_mission()
    for mission in user_mission.items:
        mst_entry = next((x for x in mst_mission.items
                          if x.MissionID == mission.MissionID), None)
        series, cfg_idx = _get_mission_cfg_idx(mission.MissionID)
        if series is None:
            continue
        cfg_item = series["Missions"][cfg_idx]
        if mst_entry is None:
            continue
        if (mst_entry.MissionType == mission_type and mission.IsAppear == 1
                and mission.MissionCompleteStatus != MissionCompleteStatus.CompleteRewardAcquired):
            log.debug("checking mission for %s: %s", gdkey, cfg_item["MissionName"])
            if mission_type in _BASIC_PROGRESS:
                _basic_progress_check(mission, progress_to_update)
            elif mission_type in _BASIC_PARAM:
                _basic_param_check(mission, progress_to_update, cfg_item["Params"][0])
            elif mission_type == MissionType.GetSpecificYokaiToLevel:
                if progress_to_update == cfg_item["Params"][0]:
                    mission.MissionParamProgress = progress_to_update2
                    if mission.MissionParamProgress >= mission.MissionParamTarget:
                        mission.MissionCompleteStatus = MissionCompleteStatus.CompletePendingReward
            elif mission_type == MissionType.CompleteStageInSeconds:
                player_stage_id = progress_to_update
                player_time = progress_to_update2
                param_stage_id = cfg_item["Params"][0]
                param_time = cfg_item["Params"][1]
                mission.MissionParamProgress = player_time
                if player_stage_id == param_stage_id and player_time <= param_time:
                    mission.MissionCompleteStatus = MissionCompleteStatus.CompletePendingReward
    if not manual_save:
        await save_user_mission(gdkey, user_mission)
    return user_mission


_MONEY_SEGMENTS = [
    (0, 19503, -9.31378239683659486e-13, 9.49718454859748785e-09, 1.65599269055426764e-03, 0.0),
    (19503, 98886, 3.54735885620046944e-14, -7.02074683060136725e-09, 9.63643205228385206e-04, 29.0),
    (98886, 730551, 4.13930576528173492e-17, -2.14673863641769430e-10, 5.19614869537963608e-04, 79.0),
    (730551, 4693781, 2.26140561025886510e-18, -3.11738313337231444e-11, 2.97958510870173878e-04, 332.0),
    (4693781, 16342265, 1.13702467628649215e-19, -4.81573027415106134e-12, 1.57421380310510930e-04, 1164.0),
    (16342265, 43639866, 9.70709432301333797e-21, -1.00454788996105275e-12, 9.15133676205519498e-05, 2524.0),
    (43639866, 87258813, 1.49992019413226535e-21, -2.99330578210795985e-13, 5.83698593381509477e-05, 4471.0),
    (87258813, 164548262, 1.50583294243071944e-22, -9.36343915347345514e-14, 4.08181909845549339e-05, 6572.0),
    (164548262, 341173912, 4.22870018286688518e-23, -3.54437707789627279e-14, 2.90428896458268666e-05, 9237.0),
    (341173912, 501126231, 1.25822833054158318e-23, -1.82651444054791573e-14, 2.04799661524042164e-05, 13494.0),
    (501126231, 1000021478, 1.69062812767858107e-24, -5.61677884535533050e-15, 1.56026052486079671e-05, 16354.0),
    (1000021478, 1501115792, 1.98692409103500659e-24, -3.90141531575173342e-15, 1.12606108162125956e-05, 22950.0),
    (1501115792, 2000028972, 1.22922693348241123e-24, -2.18841543736151449e-15, 8.84737991664937757e-06, 27863.0),
    (2000028972, 2147393648, 5.63928751381472842e-24, -2.86938696083429261e-15, 7.58163801728976713e-06, 31885.0),
]

_EXP_SEGMENTS = [
    (0, 19503, -4.48361255856927931e-12, 4.54072418115759809e-08, 8.10077200016582656e-03, 0.0),
    (19503, 98886, 1.73097170552723314e-13, -3.42942070042694355e-08, 4.75567197901465705e-03, 142.0),
    (98886, 730551, 1.95776881784349619e-16, -1.05296412884479166e-09, 2.58331681492249060e-03, 390.0),
    (730551, 4693781, 1.11372057468599232e-17, -1.54661378642014054e-10, 1.48742096434320960e-03, 1651.0),
    (4693781, 16342265, 5.71990593904137891e-19, -2.41315168916343234e-11, 7.86306421119969479e-04, 5810.0),
    (16342265, 43639866, 4.83447957840900533e-20, -5.00972216520284317e-12, 4.56950615463259588e-04, 12599.0),
    (43639866, 87258813, 7.47985780985637522e-21, -1.49449221111500470e-12, 2.91517503887367467e-04, 22323.0),
    (87258813, 164548262, 7.18498919412637178e-22, -4.65212972571956305e-13, 2.03834964531046138e-04, 32816.0),
    (164548262, 341173912, 2.30957298582560380e-22, -1.81200109349690174e-13, 1.44799058346940568e-04, 46123.0),
    (341173912, 501126231, 4.39818175640677205e-23, -8.65722555443258087e-14, 1.02405145564190197e-04, 67318.0),
    (501126231, 1000021478, 9.18133825116994149e-24, -2.87743979698713797e-14, 7.80860701691730682e-05, 81663.0),
    (1000021478, 1501115792, -2.34707446800188890e-23, -2.74323642551017038e-15, 5.62308573766058303e-05, 114598.0),
    (1501115792, 2000028972, 9.83129676638006056e-23, -6.42347810719374237e-14, 3.58014211032697520e-05, 139133.0),
    (2000028972, 2147393648, -9.59690854169443042e-22, 3.58486312713437551e-13, 4.51207919454216030e-05, 153215.0),
]


def _piecewise(score: int, segments, default: int) -> int:
    for lo, hi, a, b, c, d in segments:
        if lo <= score <= hi:
            t = score - lo
            return int(round(a * t ** 3 + b * t ** 2 + c * t + d))
    return default


def score_to_money(score: int) -> int:
    return _piecewise(score, _MONEY_SEGMENTS, 1000)


def score_to_exp(score: int) -> int:
    return _piecewise(score, _EXP_SEGMENTS, 10000)


async def give_youkai_exp(result: dict, youkai, youkai_id: int, exp_to_add: int,
                          master_youkai, gdkey: str):
    level_mst = parser_for(YwpMstYoukaiLevel,
                           game_data.get_table_string_from_json("ywp_mst_youkai_level"))
    level_open_mst = parser_for(YwpMstYoukaiLevelOpen,
                                game_data.get_table_string_from_json("ywp_mst_youkai_level_open"))

    before, after = result["before"], result["after"]
    before["level"] = youkai.Level
    before["exp"] = int(youkai.Exp)
    before["expBar"]["denominator"] = youkai.ExpDenominator
    before["expBar"]["numerator"] = youkai.ExpNumerator
    before["expBar"]["pctg"] = youkai.Percentage

    after["level"] = before["level"]
    after["exp"] = before["exp"]
    after["expBar"]["denominator"] = before["expBar"]["denominator"]
    after["expBar"]["numerator"] = before["expBar"]["numerator"]
    after["expBar"]["pctg"] = before["expBar"]["pctg"]

    if youkai.Level < master_youkai.MaxLevel and youkai.IsLockedLevel == 0:
        level_index = 0
        level = before["level"]

        cur_level_index = mst_youkai_level_index(level_mst, master_youkai.LevelType,
                                                 before["level"])
        if cur_level_index != -1 and before["exp"] < level_mst.items[cur_level_index].BaseExp:
            before["exp"] = level_mst.items[cur_level_index].BaseExp

        after["exp"] = before["exp"] + exp_to_add

        while level_index != -1:
            if level >= master_youkai.MaxLevel:
                after["level"] = master_youkai.MaxLevel
                after["expBar"]["denominator"] = 0
                after["expBar"]["numerator"] = 0
                after["expBar"]["pctg"] = 0
                break
            level_index = mst_youkai_level_index(level_mst, master_youkai.LevelType, level)
            if level_index == -1:
                break
            level += 1
            info = level_mst.items[level_index]
            if after["exp"] < info.BaseExp or after["exp"] > info.MaxExp:
                continue
            after["level"] = info.Level
            after["expBar"]["denominator"] = (info.MaxExp + 1) - info.BaseExp
            after["expBar"]["numerator"] = after["exp"] - info.BaseExp
            after["expBar"]["pctg"] = int(
                (after["expBar"]["numerator"] / after["expBar"]["denominator"]) * 100.0)
            break

        open_idx = mst_youkai_level_open_index(level_open_mst, before["level"],
                                               after["level"], master_youkai.YoukaiRarity)
        if open_idx != -1 and after["level"] < master_youkai.MaxLevel:
            after["level"] = level_open_mst.items[open_idx].Level
            youkai.IsLockedLevel = 1
            tmp_idx = mst_youkai_level_index(level_mst, master_youkai.LevelType,
                                             after["level"])
            if tmp_idx != -1:
                info = level_mst.items[tmp_idx]
                after["expBar"]["denominator"] = (info.MaxExp + 1) - info.BaseExp
                after["exp"] = info.BaseExp
                after["expBar"]["numerator"] = 0
                after["expBar"]["pctg"] = 0

    youkai.Level = after["level"]
    youkai.Exp = after["exp"]
    youkai.ExpDenominator = after["expBar"]["denominator"]
    youkai.ExpNumerator = after["expBar"]["numerator"]
    youkai.Percentage = after["expBar"]["pctg"]

    hp_offset = (master_youkai.MaxHp - master_youkai.BaseHp) // master_youkai.MaxLevel
    atk_offset = (master_youkai.MaxAtk - master_youkai.BaseAtk) // master_youkai.MaxLevel
    youkai.Hp += hp_offset * (after["level"] - before["level"])
    youkai.Atk += atk_offset * (after["level"] - before["level"])

    if youkai.IsLockedLevel == 1:
        result["isLockLevel"] = True
    if youkai.Level >= master_youkai.MaxLevel:
        result["isMaxLevel"] = True
        result["isLockLevel"] = False
        youkai.IsLockedLevel = 0
        youkai.Level = master_youkai.MaxLevel

    await mission_update_progress(gdkey, MissionType.GetSpecificYokaiToLevel,
                                  int(youkai_id), progress_to_update2=youkai.Level)
