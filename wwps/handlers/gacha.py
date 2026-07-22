from __future__ import annotations

import json
import random

from aiohttp import web

from .. import config, consts, game_data, managers, utils
from .. import user_data as manage_data
from ..dto import TutorialList, common_response_full
from ..managers import MissionType, RarityType, YokaiGetType
from ..rows import (YwpMstYoukai, YwpUserDictionary, YwpUserItem, YwpUserYoukai,
                    YwpUserYoukaiBonusEffect, YwpUserYoukaiSkill, parser_for)
from ..table_parser import TableParser
from ..ywp_user_data import YwpUserData


class PrizeType:
    Item = 1
    Yokai = 2
    ConvertItem = 4


class CapsuleColor:
    Gray = 1
    Blue = 2
    Red = 3
    Gold = 4
    FakeOutGold = 5
    Rainbow = 6


CAPSULE_CLRS = {
    RarityType.RarityE: CapsuleColor.Gray,
    RarityType.RarityD: CapsuleColor.Gray,
    RarityType.RarityC: CapsuleColor.Blue,
    RarityType.RarityB: CapsuleColor.Blue,
    RarityType.RarityA: CapsuleColor.Red,
    RarityType.RarityS: CapsuleColor.Gold,
    RarityType.RaritySS: CapsuleColor.Gold,
    RarityType.RaritySSS: CapsuleColor.Gold,
    RarityType.RarityZ: CapsuleColor.Gold,
    RarityType.RarityZZ: CapsuleColor.Gold,
    RarityType.RarityZZZ: CapsuleColor.Rainbow,
    RarityType.RarityUZ: CapsuleColor.Rainbow,
    RarityType.RarityUZP: CapsuleColor.Rainbow,
}

CONVERT_TO_ITEM = 0
REROLL_UNTIL_VALID = 1

_gachas: dict | None = None
_weight_sum_cache: dict[int, float] = {}


def _ensure_loaded():
    global _gachas
    if _gachas is None:
        _gachas = {int(k): v for k, v in json.loads(
            game_data.gamedata_cache["gacha_pool"]).items()}


async def register_yokai_and_get_prize(yokai_id: int, capsule: int, rank: int,
                                       user_yokai, user_skill, user_dict,
                                       user_item, gacha_id: int, user_bonus,
                                       gdkey: str) -> dict:
    prize_type = PrizeType.Yokai
    get_type = managers.check_get_type(yokai_id, user_yokai, user_skill)
    yokai = None
    convert_item_info = None
    item_for_convert = None
    if get_type != YokaiGetType.MaxLevel:
        yokai = managers.yokai_won_popup(yokai_id, user_yokai, user_skill)
    else:
        convert_item_info = {
            "originalPrizeType": PrizeType.Yokai,
            "originalPrizeId": yokai_id,
            "skillMaxYoukaiId": yokai_id,
        }
        item_for_convert = _gachas[gacha_id]["convertItem"][str(rank)]
        prize_type = PrizeType.ConvertItem
        managers.item_add(user_item, item_for_convert["itemId"], 1)
    await managers.add_youkai(user_yokai, yokai_id, user_skill, user_bonus, gdkey)
    managers.edit_dictionary(user_dict, yokai_id, True, True)
    return {
        "item": item_for_convert,
        "capsuleColor": capsule,
        "prizeType": prize_type,
        "icon": None,
        "ymoney": None,
        "youkai": yokai,
        "rarityType": rank,
        "convertItemInfo": convert_item_info,
    }


def _register_item(user_item_table, result_item: int) -> dict:
    idx = user_item_table.find_index([str(result_item)])
    if idx == -1:
        user_item_table.items.append(YwpUserItem(ItemId=result_item, Count=1))
    else:
        user_item_table.items[idx].Count += 1
    return {"itemId": result_item, "isLimitOver": 0, "cnt": 1}


def _pick_yokai(yokais: list, rate_up: dict | None):
    if not rate_up:
        return random.choice(yokais)
    weights = [rate_up.get(str(y), rate_up.get(y, 1.0)) for y in yokais]
    total = sum(weights)
    if total <= 0:
        return random.choice(yokais)
    roll = random.random() * total
    cumulative = 0.0
    for y, w in zip(yokais, weights):
        cumulative += w
        if roll <= cumulative:
            return y
    return yokais[-1]


def _roll_pool(weights: dict, gacha_id: int, excluded: set | None = None):
    if not excluded:
        total = _weight_sum_cache.setdefault(gacha_id, sum(weights.values()))
        roll = random.random() * total
        cumulative = 0.0
        for key, w in weights.items():
            cumulative += w
            if roll <= cumulative:
                return key
        raise RuntimeError("Invalid weights for pool roll.")
    total = sum(w for k, w in weights.items() if k not in excluded)
    if total <= 0:
        return None
    roll = random.random() * total
    cumulative = 0.0
    last = None
    for key, w in weights.items():
        if key in excluded:
            continue
        last = key
        cumulative += w
        if roll <= cumulative:
            return key
    return last


def _fallback_item_prize(gacha: dict, user_item_table, last_maxed_yokai: int,
                         last_maxed_rank: int) -> dict:
    item_for_convert = gacha["convertItem"][str(last_maxed_rank)]
    managers.item_add(user_item_table, item_for_convert["itemId"], 1)
    return {
        "youkai": None, "icon": None, "ymoney": None,
        "capsuleColor": CapsuleColor.Gray,
        "prizeType": PrizeType.ConvertItem,
        "rarityType": last_maxed_rank,
        "item": item_for_convert,
        "convertItemInfo": {
            "originalPrizeType": PrizeType.Yokai,
            "originalPrizeId": last_maxed_yokai,
            "skillMaxYoukaiId": last_maxed_yokai,
        },
    }


async def crank_reward(gacha_id: int, user_yokai, user_skill, user_dict,
                       user_item, user_bonus, gdkey: str, mode: int) -> dict | None:
    _ensure_loaded()
    if gacha_id not in _gachas:
        return None
    gacha = _gachas[gacha_id]
    excluded: set | None = None
    last_maxed_yokai = -1
    last_maxed_rank = 0

    while True:
        pool = _roll_pool(gacha["weights"], gacha_id, excluded)
        if pool is None:
            return _fallback_item_prize(gacha, user_item, last_maxed_yokai,
                                        last_maxed_rank)
        if pool.startswith("i"):
            items_to_roll = gacha["items"][pool]
            result_item = random.choice(items_to_roll)
            item_won = _register_item(user_item, result_item)
            return {
                "youkai": None, "icon": None, "ymoney": None,
                "capsuleColor": CapsuleColor.Gray,
                "prizeType": PrizeType.Item,
                "rarityType": RarityType.RarityB,
                "item": item_won,
                "convertItemInfo": None,
            }
        rank = int(pool)
        yokais_to_roll = gacha["youkai"][pool]
        result_yokai = _pick_yokai(yokais_to_roll, gacha.get("rateUp"))
        if mode == REROLL_UNTIL_VALID:
            get_type = managers.check_get_type(result_yokai, user_yokai, user_skill)
            if get_type == YokaiGetType.MaxLevel:
                candidates = [c for c in yokais_to_roll
                              if c != result_yokai and managers.check_get_type(
                                  c, user_yokai, user_skill) != YokaiGetType.MaxLevel]
                if candidates:
                    result_yokai = _pick_yokai(candidates, gacha.get("rateUp"))
                else:
                    last_maxed_yokai = result_yokai
                    last_maxed_rank = rank
                    excluded = excluded or set()
                    excluded.add(pool)
                    continue
        return await register_yokai_and_get_prize(
            result_yokai, CAPSULE_CLRS[rank], rank, user_yokai, user_skill,
            user_dict, user_item, gacha_id, user_bonus, gdkey)


def _flatten_wibwob_prize(res: dict):
    prizes = res.get("gachaPrizeList")
    if config.is_wibwob and prizes and len(prizes) == 1 and prizes[0] is not None:
        prize = prizes[0]
        res.update(prize)
        if prize.get("youkai"):
            res.update(prize["youkai"])
        if prize.get("item"):
            res.update(prize["item"])
        if prize.get("convertItemInfo"):
            res.update(prize["convertItemInfo"])
        res.pop("gachaPrizeList", None)


async def _str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


async def execute_gacha(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    gacha_id = req.get("gachaId", 0)

    _ensure_loaded()
    if gacha_id not in _gachas:
        return utils.encrypted_json(consts.msg_box_response(
            f"No pool data exists for:\ngachaId:{gacha_id}", "Error"))
    userdata = await YwpUserData.load(gdkey)
    gacha_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_gacha"])["tableData"])
    user_item = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_dict = parser_for(YwpUserDictionary,
                           await _str_table(gdkey, "ywp_user_dictionary"))
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    mst_yokai = parser_for(YwpMstYoukai, json.loads(
        game_data.gamedata_cache["ywp_mst_youkai"])["tableData"])
    tutorial_list = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))
    tutorial_changed = False
    if tutorial_list.get_status(2, 2) == 0:
        tutorial_list.edit_tutorial_flg(2, 2, 1)
        tutorial_changed = True
    items_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_item"])["tableData"])

    gacha_index = managers.get_table_index(gacha_mst, [(0, str(gacha_id))])
    if config.is_wibwob:
        pull_count = 1
    else:
        pull_count = int(gacha_mst.table[gacha_index][11])
    price_type = int(gacha_mst.table[gacha_index][3])
    price_id = int(gacha_mst.table[gacha_index][4])
    price_num = int(gacha_mst.table[gacha_index][5])

    def err():
        return utils.encrypted_json(consts.msg_box_response("Error occured", "Error"))

    if price_type == 1:
        if userdata.ymoney - price_num < 0:
            return err()
        userdata.ymoney -= price_num
    elif price_type == 2:
        item_idx = managers.get_table_index(items_mst, [(0, str(price_id))])
        if item_idx < 0:
            return err()
        item_id_action = int(items_mst.table[item_idx][1])
        number = 0
        if item_id_action == 81:
            price = price_num
            for item in items_mst.table:
                if int(item[1]) == item_id_action:
                    user_count = next((x.Count for x in user_item.items
                                       if x.ItemId == int(item[0])), 0)
                    number += user_count
                    if price - user_count <= 0:
                        managers.item_remove(user_item, int(item[0]), price)
                        break
                    elif user_count > 0:
                        price -= user_count
                        managers.item_remove(user_item, int(item[0]), user_count)
            if number - price_num < 0:
                return err()
        else:
            number = next((x.Count for x in user_item.items
                           if x.ItemId == price_id), 0)
            if number - price_num < 0:
                return err()
            managers.item_remove(user_item, price_id, price_num)

    prizes = []
    request_youkai_id = req.get("requestYoukaiId", 0)
    if request_youkai_id == 0:
        mode = REROLL_UNTIL_VALID if config.is_wibwob else CONVERT_TO_ITEM
        for _ in range(pull_count):
            prizes.append(await crank_reward(gacha_id, user_yokai, user_skill,
                                             user_dict, user_item, user_bonus,
                                             gdkey, mode))
    elif managers.gacha_choice_is_ok(gacha_id, request_youkai_id):
        yk_idx = next((i for i, x in enumerate(mst_yokai.items)
                       if x.YoukaiId == request_youkai_id), -1)
        if yk_idx == -1:
            return err()
        rarity = mst_yokai.items[yk_idx].YoukaiRarity
        prizes.append(await register_yokai_and_get_prize(
            request_youkai_id, CapsuleColor.Red, rarity, user_yokai, user_skill,
            user_dict, user_item, gacha_id, user_bonus, gdkey))
    else:
        return err()

    res = common_response_full()
    res["ywp_user_tutorial_list"] = None
    res["ywp_user_event"] = None
    res["canPossessionItemList"] = None
    res["gachaPrizeList"] = prizes
    res["effectType"] = 1
    res["ywp_user_youkai_strong_skill_diff"] = None

    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary", str(user_dict))
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill", str(user_skill))
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", str(user_yokai))
    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", str(user_item))
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   tutorial_list.serialize())
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   str(user_bonus))

    _flatten_wibwob_prize(res)
    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    res["ywp_user_dictionary"] = str(user_dict)
    res["ywp_user_youkai_skill"] = str(user_skill)
    if tutorial_changed:
        res["ywp_user_tutorial_list"] = tutorial_list.serialize()
    await managers.mission_update_progress(gdkey, MissionType.TotalCrank, 1)
    await utils.add_tables_to_response(consts.EXECUTE_GACHA_TABLES, res, True, gdkey)
    return utils.encrypted_json(res)
