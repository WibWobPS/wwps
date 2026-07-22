from __future__ import annotations

import json
import math
import random
import time
from datetime import datetime

from aiohttp import web

from .. import consts, game_data, managers, utils
from .. import user_data as manage_data
from ..dto import TutorialList, common_response_full
from ..managers import MissionCompleteStatus, MissionType, RewardType
from ..rows import (YwpMstItem, YwpMstYoukai, YwpUserItem, YwpUserMap,
                    YwpUserMission, YwpUserShopItemRemainCnt,
                    YwpUserShopItemUnlock, YwpUserStage, YwpUserYoukai,
                    YwpUserYoukaiBonusEffect, YwpUserYoukaiSkill, parser_for)
from ..table_parser import TableParser
from ..ywp_user_data import YwpUserData

UNLOCK_WITH_YMONEY = 1
UNLOCK_WITH_YOKAI = 2


async def _str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


def _mst_map() -> list[dict]:
    return json.loads(game_data.gamedata_cache["ywp_mst_map"])["data"]


async def map_(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["ywp_user_map"] = await _str_table(gdkey, "ywp_user_map")
    res["ywp_mst_map"] = _mst_map()
    res["ywp_mst_event"] = json.loads(game_data.gamedata_cache["ywp_mst_event"])
    return utils.encrypted_json(res)


class _MapUnlockError(Exception):
    pass


async def map_unlock(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    map_id = req.get("mapId", 0)
    unlock_type = req.get("unLockType", 0)

    userdata = await YwpUserData.load(gdkey)
    user_stage = parser_for(YwpUserStage, await _str_table(gdkey, "ywp_user_stage"))
    user_map = parser_for(YwpUserMap, await _str_table(gdkey, "ywp_user_map"))
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    mst_map = _mst_map()

    user_map_index = managers.map_get_index(user_map, map_id)
    mst_map_index = managers.mst_map_get_index(mst_map, map_id)
    user_stage_index = managers.stage_get_index(user_stage, int(map_id) * 1000 + 1)

    try:
        if user_map_index == -1 or mst_map_index == -1:
            raise _MapUnlockError("Invalid map")
        if user_stage_index == -1:
            raise _MapUnlockError("Invalid stage")

        entry = mst_map[mst_map_index]
        if unlock_type == UNLOCK_WITH_YMONEY:
            if entry.get("needYmoney", 0) > userdata.ymoney:
                raise _MapUnlockError("Not enough Y-Money")
            userdata.ymoney -= int(entry.get("needYmoney", 0))
        elif unlock_type == UNLOCK_WITH_YOKAI:
            target_id = entry.get("needYoukaiId", 0)
            target_level = entry.get("needYoukaiLevel", 0)
            yokai_idx = managers.get_youkai_index(user_yokai, target_id)
            if yokai_idx == -1:
                raise _MapUnlockError("You don't have the Yo-kai")
            if user_yokai.items[yokai_idx].Level < target_level:
                raise _MapUnlockError("Yo-kai not at required level")
        else:
            raise _MapUnlockError(f"Unsupported unlock type: {unlock_type}")
    except _MapUnlockError as ex:
        return utils.encrypted_json(consts.msg_box_response(str(ex), "Error"))

    await managers.refresh_ywp_user_friend(gdkey, -1, -1, userdata.playerName, -1, "")
    user_stage.items[user_stage_index].StageStatus = 0
    user_map.items[user_map_index].IsUnlocked = 1

    compiled_stage = str(user_stage)
    compiled_map = str(user_map)
    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "ywp_user_stage", compiled_stage)
    await manage_data.set_ywp_user(gdkey, "ywp_user_map", compiled_map)

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_stage"] = compiled_stage
    res["ywp_user_map"] = compiled_map
    return utils.encrypted_json(res)


async def map_warp(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    map_id = req.get("mapId", 0)

    user_tuto = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))
    unavailable_maps = json.loads(
        game_data.gamedata_cache.get("unavailable_maps", "[]")) or []
    add_tuto_maps = json.loads(
        game_data.gamedata_cache.get("map_add_tutorial", "{}")) or {}
    userdata = await YwpUserData.load(gdkey)
    user_stage = parser_for(YwpUserStage, await _str_table(gdkey, "ywp_user_stage"))
    user_map = parser_for(YwpUserMap, await _str_table(gdkey, "ywp_user_map"))
    mst_map = _mst_map()

    user_map_idx = user_map.find_index([str(map_id)])
    mst_map_idx = next((i for i, x in enumerate(mst_map)
                        if x.get("mapId") == map_id), -1)
    if mst_map_idx == -1:
        return utils.encrypted_json(
            consts.msg_box_response("Map doesn't exist", "Error"))
    if map_id in unavailable_maps:
        return utils.encrypted_json(consts.msg_box_response(
            f"{mst_map[mst_map_idx].get('mapName')}\n is under construction!",
            "Coming soon!"))
    if user_map_idx == -1:
        managers.map_add(user_map, map_id)

    for key, tuts in add_tuto_maps.items():
        if int(key) == map_id:
            for tut in tuts:
                user_tuto.edit_tutorial_flg(tut.get("tutorialType", 0),
                                            tut.get("tutorialId", 0),
                                            tut.get("tutorialStatus", 0))

    stage_id = int(f"{map_id}001")
    if user_stage.find_index([str(stage_id)]) == -1:
        entry = mst_map[mst_map_idx]
        status = 2
        if (entry.get("needYmoney", 0) == 0 and entry.get("needYoukaiId", 0) == 0
                and entry.get("needYoukaiLevel", 0) == 0
                and entry.get("needFriendPoint", 0) == 0):
            status = 0
        user_stage.items.append(YwpUserStage(StageId=stage_id, StageStatus=status))

    userdata.nowStageId = stage_id
    await managers.refresh_ywp_user_friend(gdkey, -1, -1, userdata.playerName, -1, "")

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["teamEventButtonHiddenFlg"] = 1

    maps = [m for m in mst_map if m.get("mapId") == map_id]
    if not maps:
        return utils.encrypted_json(consts.msg_box_response("Error", "Error"))
    res["ywp_mst_map"] = maps
    compiled_stage = str(user_stage)
    res["ywp_user_stage"] = compiled_stage
    res["ywp_user_map"] = str(user_map)
    res["ywp_user_tutorial_list"] = user_tuto.serialize()

    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   user_tuto.serialize())
    await manage_data.set_ywp_user(gdkey, "ywp_user_stage", compiled_stage)
    await manage_data.set_ywp_user(gdkey, "ywp_user_map", res["ywp_user_map"])

    ywp_keys = ["ywp_mst_event_condition", "ywp_user_friend_stage",
                "ywp_user_treasure_series", "ywp_user_stage_rank",
                "ywp_user_tutorial_list", "ywp_user_raid_boss",
                "ywp_user_event_condition", "ywp_user_event",
                "ywp_user_mini_game_map_friend", "ywp_user_stage_relation_progress",
                "ywp_user_icon_budge", "ywp_user_steal_progress",
                "ywp_user_mini_game_map", "ywp_user_score_attack_reward",
                "ywp_user_event_tutorial", "ywp_user_event_ranking_reward",
                "ywp_mst_event"]
    await utils.add_tables_to_response(ywp_keys, res, True, gdkey)
    return utils.encrypted_json(res)


async def login_stamp(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    login_stamp_tables: list[str] = []

    res = common_response_full()
    res.update({
        "ywp_user_data": None, "ywp_mst_login_stamp_reward": None,
        "ywp_mst_login_stamp": None, "ywp_user_login_stamp_list": None,
        "stampDt": None, "responseCode": 0, "directDistFlg": 1,
        "youkai": None, "item": None,
    })

    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))

    stamp_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_login_stamp"])["tableData"])
    reward_mst = TableParser(json.loads(
        game_data.gamedata_cache["ywp_mst_login_stamp_reward"])["tableData"])
    user_stamp = TableParser(await _str_table(gdkey, "login_stamp"))

    stamp_count = len(stamp_mst.table)
    walk = 0

    if (user_stamp.table[0][0] == "0" or user_stamp.table[0][1] == "0"
            or user_stamp.table[0][2] == "0"):
        days_since_epoch = int(time.time())
        user_stamp.table[0][0] = str(days_since_epoch)
        user_stamp.table[0][1] = str(random.randrange(1, stamp_count))
        user_stamp.table[0][2] = "1"
        walk = 1
    day = int(user_stamp.table[0][2])
    stamp_id = int(user_stamp.table[0][1])
    now_epoch = int(time.time())

    for elements in stamp_mst.table:
        if (int(elements[0]) == stamp_id
                and now_epoch > int(user_stamp.table[0][0]) + 8400
                and (day + 1) > int(elements[2])):
            stamp_id = random.randrange(1, stamp_count)
            walk = 1
            now_epoch = int(time.time())
            user_stamp.table[0][0] = str(now_epoch)
            user_stamp.table[0][1] = str(stamp_id)
            user_stamp.table[0][2] = "1"
            day = 1

    if now_epoch > int(user_stamp.table[0][0]) + 86400:
        await managers.mission_update_progress(gdkey, MissionType.TotalLoginDays, 1)
        walk = 1
        user_stamp.table[0][0] = str(now_epoch)
        day += 1
        user_stamp.table[0][2] = str(day)

    current_item_count = 0
    current_reward_id = 0
    current_reward_type = RewardType.NONE
    rewards = []
    for elements in reward_mst.table:
        if int(elements[0]) == stamp_id:
            entry = {
                "rewardItemId": int(elements[3]),
                "rewardItemType": int(elements[2]),
                "stampId": stamp_id,
                "rewardDayCnt": int(elements[1]),
                "rewardItemCnt": int(elements[4]),
            }
            if entry["rewardDayCnt"] == day:
                current_item_count = entry["rewardItemCnt"]
                current_reward_id = entry["rewardItemId"]
                current_reward_type = entry["rewardItemType"]
            rewards.append(entry)
    res["ywp_mst_login_stamp_reward"] = rewards

    stamps = []
    for elements in stamp_mst.table:
        if int(elements[0]) == stamp_id:
            stamps.append({
                "footerResName": elements[7],
                "stampId": stamp_id,
                "description": elements[1],
                "endDt": "00/00",
                "startDt": "00/00",
                "titleResName": elements[5],
                "cautionResName": elements[8] if elements[8] != "null" else "",
                "mainResName": elements[4],
                "headerResName": elements[6],
            })
    res["ywp_mst_login_stamp"] = stamps

    if walk == 1:
        if current_reward_type == RewardType.Item:
            user_item = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
            managers.item_add(user_item, current_reward_id, current_item_count)
            res["item"] = {"itemId": current_reward_id, "isLimitOver": 0,
                           "cnt": current_item_count}
            await manage_data.set_ywp_user(gdkey, "ywp_user_item", str(user_item))
            login_stamp_tables.append("ywp_user_item")
        elif current_reward_type == RewardType.Yokai:
            dictionary = managers.edit_dictionary_raw(
                TableParser(await _str_table(gdkey, "ywp_user_dictionary")),
                current_reward_id, False, True)
            await managers.add_youkai(user_yokai, current_reward_id, user_skill,
                                      user_bonus, gdkey)
            res["youkai"] = managers.yokai_won_popup(current_reward_id, user_yokai,
                                                     user_skill)
            await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary", str(dictionary))
            await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", str(user_yokai))
            await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                           str(user_skill))
            await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                           str(user_bonus))
            login_stamp_tables += ["ywp_user_youkai", "ywp_user_dictionary",
                                   "ywp_user_youkai_skill",
                                   "ywp_user_youkai_bonus_effect"]
        elif current_reward_type == RewardType.YMoney:
            userdata.ymoney += current_item_count
        elif current_reward_type == RewardType.Hitodama:
            userdata.hitodama += current_item_count
        elif current_reward_type == RewardType.Icon:
            icon_table = managers.add_icon(
                TableParser(await _str_table(gdkey, "ywp_user_player_icon")),
                int(current_reward_id))
            await manage_data.set_ywp_user(gdkey, "ywp_user_player_icon",
                                           str(icon_table))
            login_stamp_tables.append("ywp_user_player_icon")

    res["ywp_user_login_stamp_list"] = [{
        "loginDayCnt": day, "userId": userdata.userId, "stampId": stamp_id,
        "isStep": walk}]
    res["stampDt"] = datetime.today().strftime("%Y-%m-%d")

    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "login_stamp", str(user_stamp))
    res["ywp_user_data"] = userdata.to_dict()
    await utils.add_tables_to_response(login_stamp_tables, res, True, gdkey)
    return utils.encrypted_json(res)


async def use_item(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    item_id = req.get("itemId", 0)
    youkai_id = req.get("youkaiId", 0)

    mst_item = parser_for(YwpMstItem,
                          game_data.get_table_string_from_json("ywp_mst_item"))
    item_info = next((x for x in mst_item.items if x.ItemID == item_id), None)
    if item_info is None:
        return utils.encrypted_json(consts.msg_box_response(
            "Error while fetching data for item.", "Error"))

    res = common_response_full()
    res["itemType"] = item_info.ItemType
    res["ywp_user_icon_budge"] = await _str_table(gdkey, "ywp_user_icon_budge")
    res["ywp_user_dictionary"] = await _str_table(gdkey, "ywp_user_dictionary")
    res["youkaiExp"] = None
    res["youkaiSkillExp"] = None

    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_item = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))

    def spend_item():
        entry = next((x for x in user_item.items if x.ItemId == item_id), None)
        if entry is None or entry.Count == 0:
            raise KeyError("Not enough of item")
        entry.Count -= 1

    try:
        if item_info.ItemType == managers.ItemType.Exporb:
            spend_item()
            mst_yokai = parser_for(
                YwpMstYoukai, game_data.get_table_string_from_json("ywp_mst_youkai"))
            yokai_to_give = next(x for x in user_yokai.items
                                 if x.YoukaiId == youkai_id)
            mst_entry = next(x for x in mst_yokai.items if x.YoukaiId == youkai_id)
            result = managers.user_youkai_result_res(yokai_to_give, mst_entry)
            await managers.give_youkai_exp(result, yokai_to_give, youkai_id,
                                           item_info.ItemParam, mst_entry, gdkey)
            res["youkaiExp"] = result
        elif item_info.ItemType == managers.ItemType.SoultBooster:
            skill_item = next(x for x in user_skill.items if x.YoukaiId == youkai_id)
            if skill_item.Level >= 7:
                return utils.encrypted_json(
                    consts.msg_box_response("S-Move is at max level.", "Max level"))
            spend_item()
            skill_res = managers.add_exp_to_skill(user_skill, youkai_id,
                                                  item_info.ItemParam)
            after = skill_res["after"]
            skill_item.Points = after["exp"]
            skill_item.Level = after["level"]
            skill_item.PercentageDenominator = after["expBar"]["denominator"]
            skill_item.PercentageNumerator = after["expBar"]["numerator"]
            skill_item.Percentage = after["expBar"]["pctg"]
            res["youkaiSkillExp"] = {
                "isMaxLevel": skill_res["isMaxLevel"],
                "before": skill_res["before"],
                "after": after,
                "youkaiId": youkai_id,
            }
        elif item_info.ItemType == managers.ItemType.BonusEffectBooster:
            bonus_item = next((x for x in user_bonus.items
                               if x.YoukaiID == youkai_id), None)
            if bonus_item is None:
                return utils.encrypted_json(consts.msg_box_response(
                    "Yo-kai does not have bonus effect.", "Error"))
            if bonus_item.BonusEffectLevel == 5:
                return utils.encrypted_json(consts.msg_box_response(
                    "Yo-kai is at max bonus effect level.", "Error"))
            spend_item()
            bonus_item.BonusEffectLevel += 1
    except KeyError:
        return utils.encrypted_json(
            consts.msg_box_response("You don't have the item.", "Error"))
    except Exception:
        return utils.encrypted_json(
            consts.msg_box_response("An error has occured.", "Error"))

    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_youkai_skill"] = str(user_skill)
    res["ywp_user_item"] = str(user_item)
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", res["ywp_user_item"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                   res["ywp_user_youkai_skill"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   res["ywp_user_youkai_bonus_effect"])
    await managers.mission_update_progress(gdkey, MissionType.UseTotalItems, 1)
    return utils.encrypted_json(res)


async def buy_item(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    goods_id = req.get("goodsId", 0)
    goods_count = req.get("cnt", 0)

    user_shop = parser_for(YwpUserShopItemUnlock,
                           await _str_table(gdkey, "ywp_user_shop_item_unlock"))
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_icon_budge"] = await _str_table(gdkey, "ywp_user_icon_budge")
    res["itemId"] = 0
    res["cnt"] = 0
    res["ywp_user_shop_item_remain_cnt"] = await _str_table(
        gdkey, "ywp_user_shop_item_remain_cnt")
    res["ywp_user_data"] = None

    item_list = json.loads(game_data.gamedata_cache["ywp_mst_shop_item_list"])["data"]
    item = next((x for x in item_list if x.get("goodsId") == goods_id), None)
    if item is None:
        return utils.encrypted_json(consts.msg_box_response(
            f"Item with ID {goods_id}\nnot found.", "Item not found"))
    if goods_count <= 0 or goods_count > 99:
        return utils.encrypted_json(
            consts.msg_box_response("Invalid quantity.", "Error"))
    if item.get("lockConditionFlg") == 1:
        if not any(x.ItemID == item.get("itemId") for x in user_shop.items):
            return utils.encrypted_json(
                consts.msg_box_response("Item not unlocked", "Item not found"))
    if goods_count * item.get("price", 0) > userdata.ymoney:
        return utils.encrypted_json(consts.msg_box_response(
            "You don't have enough Y-Money.", "Not enough Y-Money"))

    if item.get("limitCnt", 0) > 0:
        await managers.check_shop_limit_reset(gdkey)
        remain = parser_for(YwpUserShopItemRemainCnt,
                            await _str_table(gdkey, "ywp_user_shop_item_remain_cnt"))
        remain_item = next((x for x in remain.items if x.ItemID == item["goodsId"]),
                           None)
        if remain_item is None:
            remain_item = YwpUserShopItemRemainCnt(ItemID=goods_id, AlreadyBought=0)
            remain.items.append(remain_item)
        if remain_item.AlreadyBought + goods_count <= item["limitCnt"]:
            remain_item.AlreadyBought += goods_count
            res["ywp_user_shop_item_remain_cnt"] = str(remain)
            await manage_data.set_ywp_user(gdkey, "ywp_user_shop_item_remain_cnt",
                                           res["ywp_user_shop_item_remain_cnt"])
        else:
            return utils.encrypted_json(consts.msg_box_response(
                "Item is out of stock for today.", "Out of stock"))

    userdata.ymoney -= item.get("price", 0) * goods_count

    user_items = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
    item_idx = user_items.find_index([str(goods_id)])
    if item_idx == -1:
        user_items.items.append(YwpUserItem(ItemId=goods_id, Count=goods_count))
    else:
        user_items.items[item_idx].Count += goods_count

    user_mission = await managers.mission_update_progress(
        gdkey, MissionType.TotalPurchaseShop, goods_count, None, True)
    await managers.mission_update_progress(
        gdkey, MissionType.BuySpecificItemAtShop, goods_id, user_mission, True)
    await managers.save_user_mission(gdkey, user_mission)
    res["ywp_user_item"] = str(user_items)
    res["ywp_user_data"] = userdata.to_dict()
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", res["ywp_user_item"])
    await userdata.save(gdkey)
    return utils.encrypted_json(res)


async def buy_hitodama(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    good = next((x for x in managers.shop_hitodama_data()
                 if x.get("goodsId") == req.get("goodsId")), None)
    if good is None:
        return web.Response(status=400, text="Invalid GoodID")
    userdata = await YwpUserData.load(gdkey)
    before = {"freeHitodama": userdata.freeHitodama, "hitodama": userdata.hitodama}
    if userdata.ymoney < good.get("price", 0):
        return utils.encrypted_json(consts.msg_box_response(
            "You don't have enough Y Money", "Too expensive"))
    userdata.buy_hitodama_good(good.get("price", 0), good.get("sellCnt", 0),
                               good.get("bonusCnt", 0))
    await userdata.save(gdkey)
    res = common_response_full()
    res["before"] = before
    res["after"] = {"freeHitodama": userdata.freeHitodama,
                    "hitodama": userdata.hitodama}
    res["ywp_user_data"] = userdata.to_dict()
    return utils.encrypted_json(res)


async def get_mission(request: web.Request,
                      already_reward_is_appear: int = 0) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    mst_mission = json.loads(
        game_data.gamedata_cache["ywp_mst_mission"])["tableData"]
    mst_daily = json.loads(
        game_data.gamedata_cache["ywp_mst_daily_event_mission"])["tableData"]
    user_mission = parser_for(YwpUserMission,
                              await _str_table(gdkey, "ywp_user_mission"))
    userdata = await YwpUserData.load(gdkey)
    managers.sort_user_mission(user_mission, already_reward_is_appear, True)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["ywp_mst_mission"] = mst_mission
    res["ywp_user_mission"] = str(user_mission)
    res["ywp_mst_daily_event_mission"] = mst_daily
    await manage_data.set_ywp_user(gdkey, "ywp_user_mission", str(user_mission))
    return utils.encrypted_json(res)


async def mission_reward(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    mission_id = req.get("missionId", 0)

    user_mission = parser_for(YwpUserMission,
                              await _str_table(gdkey, "ywp_user_mission"))
    userdata = await YwpUserData.load(gdkey)
    user_item = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_dict = TableParser(await _str_table(gdkey, "ywp_user_dictionary"))
    user_shop = parser_for(YwpUserShopItemUnlock,
                           await _str_table(gdkey, "ywp_user_shop_item_unlock"))
    user_icon = TableParser(await _str_table(gdkey, "ywp_user_player_icon"))
    user_title = TableParser(await _str_table(gdkey, "ywp_user_player_title"))
    managers.sort_user_mission(user_mission, 0, True)

    u_mission_item = next((x for x in user_mission.items
                           if x.MissionID == mission_id), None)
    if u_mission_item is None:
        return utils.encrypted_json(
            consts.msg_box_response("Can't find mission", "Err"))
    if u_mission_item.MissionCompleteStatus != MissionCompleteStatus.CompletePendingReward:
        return utils.encrypted_json(consts.msg_box_response(
            "Can't get reward for this mission", "Err"))
    mst_item = next((x for x in managers.get_mst_mission().items
                     if x.MissionID == mission_id), None)
    if mst_item is None:
        return utils.encrypted_json(
            consts.msg_box_response("Can't find mission", "Err"))

    res = {
        "ywp_mst_mission": str(managers.get_mst_mission()),
        "ywp_user_data": None,
        "responseRewardStatus": 1,
        "item": None,
        "youkai": None,
        "rewardUpMissionIdList": [],
    }

    rt = mst_item.RewardType
    if rt == RewardType.YMoney:
        userdata.ymoney += mst_item.YMoneySpiritCount
    elif rt == RewardType.Hitodama:
        userdata.hitodama += mst_item.YMoneySpiritCount
    elif rt == RewardType.Icon:
        if not any(row[0] == str(mst_item.RewardID) for row in user_icon.table):
            user_icon.add_row([str(mst_item.RewardID)])
    elif rt == RewardType.Title:
        if not any(row[0] == str(mst_item.RewardID) for row in user_title.table):
            user_title.add_row([str(mst_item.RewardID)])
    elif rt == RewardType.Item:
        res["item"] = {"itemId": mst_item.RewardID, "isLimitOver": 0, "cnt": 1}
        managers.item_add(user_item, mst_item.RewardID, 1)
    elif rt == RewardType.Yokai:
        res["youkai"] = managers.yokai_won_popup(mst_item.RewardID, user_yokai,
                                                 user_skill)
        await managers.add_youkai(user_yokai, mst_item.RewardID, user_skill,
                                  user_bonus, gdkey, user_mission, True)
        user_dict = managers.edit_dictionary_raw(user_dict, mst_item.RewardID,
                                                 True, True)
    elif rt == RewardType.AddItemToShop:
        user_shop.items.append(YwpUserShopItemUnlock(ItemID=mst_item.RewardID))
    elif rt == RewardType.IncreaseMaxFriends:
        userdata.friendMaxCnt += 1
    else:
        return utils.encrypted_json(
            consts.msg_box_response("Unsupported reward type.", "Err"))

    u_mission_item.MissionCompleteStatus = MissionCompleteStatus.CompleteRewardAcquired
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_youkai_skill"] = str(user_skill)
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    await managers.try_unlock_next_mission(mission_id, user_mission, user_yokai)
    managers.sort_user_mission(user_mission, 0, False)
    res["ywp_user_mission"] = str(user_mission)
    res["ywp_user_item"] = str(user_item)
    res["ywp_user_shop_item_unlock"] = str(user_shop)
    res["ywp_user_player_icon"] = str(user_icon)
    res["ywp_user_player_title"] = str(user_title)
    res["ywp_user_dictionary"] = str(user_dict)

    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                   res["ywp_user_youkai_skill"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   res["ywp_user_youkai_bonus_effect"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_player_icon",
                                   res["ywp_user_player_icon"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_player_title",
                                   res["ywp_user_player_title"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_mission", res["ywp_user_mission"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", res["ywp_user_item"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary",
                                   res["ywp_user_dictionary"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_shop_item_unlock",
                                   res["ywp_user_shop_item_unlock"])
    return utils.encrypted_json(res)
