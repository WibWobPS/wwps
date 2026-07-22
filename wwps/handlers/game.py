from __future__ import annotations

import json
import math
import time
from datetime import datetime

from aiohttp import web

from .. import (config, consts, game_data, logging_setup, managers, metrics,
                security, utils)
from .. import user_data as manage_data
from ..dto import LotYoukaiInfoList, TutorialList, common_response_full
from ..managers import MasterStageData, MissionType
from ..rows import (YwpMstYoukai, YwpMstYoukaiLevel, YwpMstYoukaiLevelOpen,
                    YwpUserDictionary, YwpUserItem, YwpUserMap, YwpUserMenufunc,
                    YwpUserStage, YwpUserYoukai, YwpUserYoukaiBonusEffect,
                    YwpUserYoukaiDeck, YwpUserYoukaiSkill, parser_for)
from ..table_parser import TableParser
from ..ywp_user_data import YwpUserData
from .. import logging_setup, metrics

log = logging_setup.get(__name__)

GAME_END = 0
GAME_RETIRE = 1


async def _str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


def _mst_table_str(name: str) -> str:
    return json.loads(game_data.gamedata_cache[name])["tableData"]


async def game_use_item(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    item_table = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
    item = next((x for x in item_table.items if x.ItemId == req.get("itemId")), None)
    if item is None or item.Count <= 0:
        return utils.encrypted_json(
            consts.msg_box_response("You don't have the item", "Err"))
    item.Count -= 1
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", str(item_table))
    await managers.mission_update_progress(gdkey, MissionType.UseSpecificItemInBattle,
                                           req.get("itemId", 0))
    await managers.mission_update_progress(gdkey, MissionType.UseTotalItems, 1)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["itemId"] = req.get("itemId")
    res["ywp_user_item"] = str(item_table)
    return utils.encrypted_json(res)


async def game_continue(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    if userdata.ymoney < 500:
        return utils.encrypted_json(consts.msg_box_response(
            "You don't have enough Ymoney.", "Not Enough Ymoney"))
    userdata.ymoney -= 500
    await userdata.save(gdkey)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    return utils.encrypted_json(res)


def _game_start_response_base(userdata: YwpUserData) -> dict:
    res = common_response_full()
    res.update({
        "userYoukaiList": [],
        "firstClearItemFlg": 0,
        "youkaiHP": 0,
        "responseCodeTeamEvent": int(game_data.gamedata_cache["responseCodeTeamEvent"]),
        "ywp_user_data": userdata.to_dict(),
        "ywp_user_dictionary_diff": "",
        "themeList": [],
        "scoreLogSendFlg": 0,
        "themeScoreCoef": "",
        "chanceAddRateEventBlock": 0,
        "addHPByWatchEffect": 0,
        "eventPointUpItemId": 0,
        "stageType": 0,
        "enemyYoukaiList": [],
        "battleType": 1,
        "eventPointMaterial": "",
        "addHPByGokuEffect": 0,
        "eventFlg": 0,
        "addAtkByGokuEffect": 0,
        "eventStatus": 0,
        "requestId": "0",
        "itemDropMaxCnt": 2,
    })
    return res


def _have_enough_hitodama(userdata: YwpUserData) -> bool:
    more_or_equal_5 = (userdata.hitodama + userdata.freeHitodama) >= 5
    if userdata.hitodama <= 0 and userdata.freeHitodama <= 0:
        return False
    if userdata.hitodama > 0:
        userdata.hitodama -= 1
    else:
        userdata.freeHitodama -= 1
    if more_or_equal_5 and (userdata.hitodama + userdata.freeHitodama) < 5:
        userdata.hitodamaRecoverSec = 900
    return True


async def _is_first_clear(stage_id: int, gdkey: str) -> bool:
    user_stage = parser_for(YwpUserStage, await _str_table(gdkey, "ywp_user_stage"))
    idx = user_stage.find_index([str(stage_id)])
    if idx == -1:
        user_stage.add_item(YwpUserStage(StageId=stage_id))
        await manage_data.set_ywp_user(gdkey, "ywp_user_stage", str(user_stage))
        return True
    return user_stage.items[idx].StageStatus == 0


def _empty_enemy(enemy_id: int, hp: int, atk: int, action_turn: int) -> dict:
    return {
        "lotTreasureInfoList": [],
        "lotItemInfoList": "0000",
        "hp": hp,
        "enemyId": enemy_id,
        "lotYoukaiInfoList": LotYoukaiInfoList([]).serialize(),
        "actionTurn": action_turn,
        "dropItemType": 0,
        "dropItemCnt": 0,
        "dropItemId": 0,
        "invalidFoodFlg": 0,
        "lotTreasureFlg": 0,
        "enableFoodInfoList": [],
        "atkPower": atk,
        "replaceYoukaiId": 0,
    }


async def game_start(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    stage_id = req.get("stageId", 0)
    userdata = await YwpUserData.load(gdkey)
    if userdata is None:
        return utils.bad_request()

    stage_items = MasterStageData.stage_items()
    stage_info_idx = next((i for i, x in enumerate(stage_items)
                           if x["StageId"] == stage_id), -1)
    if stage_info_idx != -1 and stage_items[stage_info_idx]["UseActionType"] == 1:
        user_item = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
        pass_item_id = stage_items[stage_info_idx]["UseActionID"]
        item_idx = next((i for i, x in enumerate(user_item.items)
                         if x.ItemId == pass_item_id), -1)
        if item_idx != -1 and user_item.items[item_idx].Count > 0:
            user_item.items[item_idx].Count -= 1
            await manage_data.set_ywp_user(gdkey, "ywp_user_item", str(user_item))
        else:
            return utils.encrypted_json(
                consts.msg_box_response("You don't have the pass.", "Error"))
    else:
        if not _have_enough_hitodama(userdata):
            return utils.encrypted_json(consts.msg_box_response(
                "You don't have enough spirit.", "Not Enough spirit"))

    res = _game_start_response_base(userdata)

    enemy_params = TableParser(_mst_table_str("ywp_mst_youkai_enemy_param"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    user_sskill = TableParser(await _str_table(gdkey, "ywp_user_youkai_strong_skill"))
    mst_yokai = parser_for(YwpMstYoukai, _mst_table_str("ywp_mst_youkai"))
    user_deck = parser_for(YwpUserYoukaiDeck,
                           await _str_table(gdkey, "ywp_user_youkai_deck"))
    tutorial_list = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))

    level_data_all = json.loads(game_data.gamedata_cache["stage_data"])
    if stage_info_idx == -1 or str(stage_id) not in level_data_all:
        return utils.encrypted_json(consts.msg_box_response(
            f"WibWobPS dosent have\nconfig data for this stageId : {stage_id}",
            "Missing stageId"))
    level_data = level_data_all[str(stage_id)]
    if not level_data.get("enemy"):
        return utils.bad_request()

    res["firstClearItemFlg"] = 1 if await _is_first_clear(stage_id, gdkey) else 0

    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    is_super_shrine = bool(await manage_data.get_ywp_user(gdkey, "ywp_user_addition"))
    is_after_jibanyan = tutorial_list.get_status(1, 2) == 1

    enemy_list: list[dict] = []

    def add_enemy(enemy_id: int, is_def_befriend: int, hp: int = -1, atk: int = -1):
        idx = enemy_params.find_index([str(enemy_id)])
        if idx == -1:
            return
        if hp == -1:
            hp = int(enemy_params.table[idx][2])
        if atk == -1:
            atk = int(enemy_params.table[idx][3])
        item = _empty_enemy(enemy_id, hp, atk, int(enemy_params.table[idx][4]))
        yokai_id = int(enemy_params.table[idx][1])
        enemy_mst = next((x for x in mst_yokai.items if x.YoukaiId == yokai_id), None)
        befriendable = enemy_mst is not None and enemy_mst.FoodType != 0
        skill_idx = managers.get_youkai_skill_index(user_skill, enemy_id)
        is_max_skill = skill_idx != -1 and user_skill.items[skill_idx].Level >= 7
        not_have_yokai = not any(x.YoukaiId == yokai_id for x in user_yokai.items)
        autobefriend = is_def_befriend == 1 and not_have_yokai
        if autobefriend:
            befrienders = managers.get_befriender_spots(user_deck, user_skill)
            entries = managers.generate_lot_youkai(
                befrienders, enemy_mst.YoukaiRarity, is_super_shrine, True)
            item["lotYoukaiInfoList"] = LotYoukaiInfoList(entries).serialize()
        elif (enemy_mst is not None and enemy_mst.YoukaiRarity != 0
              and befriendable and is_after_jibanyan and not is_max_skill):
            befrienders = managers.get_befriender_spots(user_deck, user_skill)
            entries = managers.generate_lot_youkai(
                befrienders, enemy_mst.YoukaiRarity, is_super_shrine, False)
            item["lotYoukaiInfoList"] = LotYoukaiInfoList(entries).serialize()
        enemy_list.append(item)

    for entry in level_data["enemy"]:
        add_enemy(entry["id"], entry.get("defBefriends", 0))

    rare_enemy_id = managers.rare_enemy_get_drop(stage_id)
    if rare_enemy_id != -1 and is_after_jibanyan and enemy_list:
        general_atk_avg = int(sum(x["atkPower"] for x in enemy_list) / len(enemy_list))
        general_hp_avg = int(sum(x["hp"] for x in enemy_list) / len(enemy_list))
        if len(enemy_list) == 3:
            weakest = min(enemy_list, key=lambda x: (x["atkPower"] + x["hp"]) / 2)
            enemy_list.remove(weakest)
        add_enemy(rare_enemy_id, 0, general_hp_avg, general_atk_avg)

    res["enemyYoukaiList"] = enemy_list
    await manage_data.set_ywp_user(gdkey, "last_enemy", enemy_list)

    def add_to_user_youkai_list(youkai_id: int):
        info_idx = managers.get_youkai_index(user_yokai, youkai_id)
        if info_idx == -1:
            return
        skill_idx = user_skill.find_index([str(youkai_id)])
        sskill_idx = user_sskill.find_index([str(youkai_id)])
        item = {
            "youkaiId": user_yokai.items[info_idx].YoukaiId,
            "skillLv": 0,
            "sSkillLv": 0,
            "hp": user_yokai.items[info_idx].Hp,
            "atkPower": user_yokai.items[info_idx].Atk,
        }
        if sskill_idx != -1:
            item["sSkillLv"] = int(user_sskill.table[sskill_idx][1])
        if skill_idx != -1:
            item["skillLv"] = user_skill.items[skill_idx].Level
        res["userYoukaiList"].append(item)

    deck = user_deck.items[0]
    for yid in (deck.MiddleYoukaiId, deck.MiddleLeftYoukaiId,
                deck.MiddleRightYoukaiId, deck.FarLeftYoukaiId,
                deck.FarRightYoukaiId):
        add_to_user_youkai_list(yid)

    unities: dict[int, int] = {}
    for yokai in res["userYoukaiList"]:
        mst_item = next((x for x in mst_yokai.items
                         if x.YoukaiId == yokai["youkaiId"]), None)
        if mst_item is None:
            continue
        unities[mst_item.YoukaiKind] = unities.get(mst_item.YoukaiKind, 0) + 1
    for yokai in res["userYoukaiList"]:
        mst_item = next((x for x in mst_yokai.items
                         if x.YoukaiId == yokai["youkaiId"]), None)
        if mst_item is None:
            continue
        unity_size = unities[mst_item.YoukaiKind]
        multiplier = {2: 10, 3: 20, 4: 25, 5: 30}.get(unity_size, 0)
        if multiplier > 0:
            log.debug("tribe unity bonus for tribe %s: %d%%",
                      mst_item.YoukaiKind, multiplier)
            yokai["hp"] += yokai["hp"] * multiplier // 100
            yokai["atkPower"] += yokai["atkPower"] * multiplier // 100

    tut_edit = level_data.get("tutorial_edit")
    if tut_edit and tut_edit.get("requests"):
        for item in tut_edit["requests"]:
            if item.get("firstClear", 0) == 0 or (
                    item.get("firstClear") == 1 and res["firstClearItemFlg"] == 1):
                idx = tutorial_list.get_tutorial_flg_index(
                    item.get("tutorialId", 0), item.get("tutorialType", 0))
                if idx == -1:
                    tutorial_list.entries.append(dict(item))
                tutorial_list.edit_tutorial_flg(item.get("tutorialType", 0),
                                                item.get("tutorialId", 0),
                                                item.get("tutorialStatus", 0))
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   tutorial_list.serialize())

    res["youkaiHP"] = 0
    res["stageType"] = stage_items[stage_info_idx]["StageType"]
    res["battleType"] = req.get("battleType", 0)
    res["requestId"] = str(int(time.time() * 1000))
    dictionary = TableParser(await _str_table(gdkey, "ywp_user_dictionary"))
    res["ywp_user_dictionary_diff"] = str(dictionary)
    await manage_data.set_ywp_user(gdkey, "ywp_user_requestid", res["requestId"])
    metrics.incr("battles_started")
    res["ywp_user_data"] = userdata.to_dict()
    await userdata.save(gdkey)
    await utils.add_tables_to_response(consts.GAME_START_TABLES, res, True, gdkey)
    return utils.encrypted_json(res)


def _game_end_response_base() -> dict:
    res = common_response_full()
    res.update({
        "teamEventButtonHiddenFlg": 0,
        "natureEventPoint": 0.0,
        "userYoukaiResultList": [],
        "eventPoint": 0,
        "eventStatus": 0,
        "responseCodeTeamEvent": 0,
        "userGameResultData": managers.user_game_result_data(),
        "eventTeamPoint": 0,
        "eventPointUpItemId": 0,
        "eventSubPoint": 0,
        "eventStatusCode": 0,
        "hpRecoverFlg": 0,
        "truncateItemList": [],
        "userItemResultList": [],
        "lockedStageResultList": [],
        "youkai": None,
    })
    return res


async def _handle_user_youkai(req: dict, res: dict, user_youkai_table, gdkey: str):
    mst_yokai = parser_for(YwpMstYoukai, _mst_table_str("ywp_mst_youkai"))
    for i in req.get("userYoukaiResultList") or []:
        yid = i.get("youkaiId", 0)
        youkai_idx = managers.get_youkai_index(user_youkai_table, yid)
        mst_idx = managers.mst_youkai_get_index(mst_yokai, yid)
        if youkai_idx < 0 or mst_idx < 0:
            continue
        item = managers.user_youkai_result_res(
            user_youkai_table.items[youkai_idx], mst_yokai.items[mst_idx])
        await managers.give_youkai_exp(item, user_youkai_table.items[youkai_idx],
                                       yid, res["userGameResultData"]["exp"],
                                       mst_yokai.items[mst_idx], gdkey)
        res["userYoukaiResultList"].append(item)


def _handle_stage(req: dict, res: dict, ywp_user_stage, ywp_user_map,
                  level_data: dict) -> int:
    first_clear = 0
    mst_map = json.loads(game_data.gamedata_cache["ywp_mst_map"])["data"]
    stage_id = req.get("stageId", 0)
    grd = res["userGameResultData"]

    stage_index = managers.stage_get_index(ywp_user_stage, stage_id)
    if stage_index == -1:
        first_clear = 1
        managers.stage_add(ywp_user_stage, stage_id)
        stage_index = managers.stage_get_index(ywp_user_stage, stage_id)
    if ywp_user_stage.items[stage_index].StageStatus == 0:
        first_clear = 1
    grd["prevScore"] = int(ywp_user_stage.items[stage_index].Score)
    if req.get("score", 0) > grd["prevScore"]:
        grd["scoreUpdateFlg"] = 1

    condition_count = 1
    secret_stage_skipp = 0
    while True:
        temp_condition_id = stage_id * 10 + condition_count
        temp_index = MasterStageData.get_stage_condition_index(temp_condition_id)
        if temp_index == -1:
            break
        cond = MasterStageData.condition_items()[temp_index]
        stage = ywp_user_stage.items[managers.stage_get_index(ywp_user_stage, stage_id)]
        good = managers.compute_stage_condition(
            cond.ConditionType, req, stage, cond.ConditionVal1, cond.ConditionVal2,
            cond.ConditionVal3)
        log.debug("condition %s type %s -> %s", temp_condition_id,
                  cond.ConditionType, good)
        if condition_count == 1:
            grd["starGetFlg1"] = 1 if good else 0
        elif condition_count == 2:
            grd["starGetFlg2"] = 1 if good else 0
        elif condition_count == 3:
            grd["starGetFlg3"] = 1 if good else 0
        elif condition_count >= 4 and good:
            new_added_stage = -1
            is_final_stage_map = MasterStageData.get_next_stage(stage_id) == -1
            pass
            map_index = managers.mst_map_get_index(mst_map, stage_id // 1000)
            if is_final_stage_map and map_index != -1 and \
                    mst_map[map_index].get("reverseMapId", 0) != 0:
                map_index2 = managers.mst_map_get_index(
                    mst_map, mst_map[map_index]["reverseMapId"])
                if map_index2 != -1:
                    rid = mst_map[map_index2]["mapId"]
                    if managers.map_get_index(ywp_user_map, rid) == -1:
                        managers.map_add(ywp_user_map, rid)
                    managers.map_update(ywp_user_map, rid, 1)
                    new_id = rid * 1000 + 1
                    if managers.stage_get_index(ywp_user_stage, new_id) == -1:
                        managers.stage_add(ywp_user_stage, new_id)
                        new_added_stage = new_id
            else:
                new_stage_id = MasterStageData.get_unlocked_secret_stage(
                    stage_id, secret_stage_skipp)
                if new_stage_id != -1:
                    if managers.stage_get_index(ywp_user_stage, new_stage_id) == -1:
                        managers.stage_add(ywp_user_stage, new_stage_id)
                        new_added_stage = new_stage_id
            if new_added_stage != -1:
                res["lockedStageResultList"].append({
                    "stageId": new_added_stage,
                    "title": getattr(cond, "OpenStageIdList", ""),
                    "conditionType": cond.ConditionType,
                    "description": cond.Description,
                    "originStageId": 0,
                })
            secret_stage_skipp += 1
        condition_count += 1

    managers.stage_edit(ywp_user_stage, stage_id, 1, req.get("score", 0),
                        grd["starGetFlg1"], grd["starGetFlg2"], grd["starGetFlg3"],
                        ywp_user_stage.items[stage_index].NumClear + 1)

    map_locked = [False]
    next_stage = [MasterStageData.get_next_stage(stage_id)]
    alt_unlock = level_data.get("altUnlock")

    def unlock_map(map_id):
        mst_index = managers.mst_map_get_index(mst_map, map_id)
        if mst_index == -1:
            return
        mid = mst_map[mst_index]["mapId"]
        if managers.map_get_index(ywp_user_map, mid) == -1:
            map_locked[0] = bool(mst_map[mst_index].get("textUnlock"))
            managers.map_add(ywp_user_map, mid)
        managers.map_update(ywp_user_map, mid, 1)
        next_stage[0] = mid * 1000 + 1

    if alt_unlock is None or alt_unlock == [-1]:
        stage_item = next((x for x in MasterStageData.stage_items()
                           if x["StageId"] == stage_id), None)
        if next_stage[0] == -1 and stage_item and stage_item["StageType"] != 2:
            og_map_index = managers.mst_map_get_index(mst_map, stage_id // 1000)
            if og_map_index != -1:
                og_map = mst_map[og_map_index]
                if og_map.get("nextMapId", 0) != 0:
                    unlock_map(og_map["nextMapId"])
                if og_map.get("extraMapId", 0) != 0:
                    unlock_map(og_map["extraMapId"])
        if next_stage[0] != -1 and \
                managers.stage_get_index(ywp_user_stage, next_stage[0]) == -1:
            if not map_locked[0]:
                managers.stage_add(ywp_user_stage, next_stage[0])
            res["lockedStageResultList"].append({
                "stageId": next_stage[0], "title": "", "conditionType": 0,
                "description": "", "originStageId": 0})
    elif alt_unlock == [0]:
        return first_clear
    else:
        for stage in alt_unlock:
            if managers.stage_get_index(ywp_user_stage, stage) == -1:
                if not map_locked[0]:
                    managers.stage_add(ywp_user_stage, next_stage[0])
                res["lockedStageResultList"].append({
                    "stageId": next_stage[0], "title": "", "conditionType": 0,
                    "description": "", "originStageId": 0})
    return first_clear


def _handle_tutorial(res: dict, tutorial_list: TutorialList | None,
                     level_data: dict, first_clear: int):
    tut_edit = level_data.get("tutorial_edit")
    if tut_edit and tut_edit.get("response"):
        for item in tut_edit["response"]:
            if tutorial_list is not None and (
                    item.get("firstClear", 0) == 0
                    or (item.get("firstClear") == 1 and first_clear == 1)):
                tutorial_list.edit_tutorial_flg(item.get("tutorialType", 0),
                                                item.get("tutorialId", 0),
                                                item.get("tutorialStatus", 0))


def _handle_menufunc(level_data: dict, menufunc_table, first_clear: int):
    for item in level_data.get("menufunc_edit") or []:
        local = next((x for x in menufunc_table.items
                      if x.AppId == item["id"]), None)
        if local is None or local.AppFlg == 0:
            managers.menufunc_add(menufunc_table, item["id"], int(item["value"]))


class _YokaiNotOnStage(Exception):
    pass


async def _handle_drop(req: dict, res: dict, dictionary_table, dictionary_diff,
                       user_youkai_table, user_skill_table, user_item_table,
                       player_icon_table_box, userdata: YwpUserData,
                       level_data: dict, first_clear: int, user_bonus, gdkey: str,
                       user_deck=None):
    mst_enemy_param = TableParser(_mst_table_str("ywp_mst_youkai_enemy_param"))
    last_enemies = await manage_data.get_ywp_user(gdkey, "last_enemy") or []
    grd = res["userGameResultData"]
    pattern = ("00000" if user_deck is None
               else security.build_lot_pattern(req, user_deck.items[0]))
    for i in req.get("enemyYoukaiResultList") or []:
        enemy_id = i.get("enemyId", 0)
        idx = mst_enemy_param.find_index([str(enemy_id)])
        stored = next((e for e in last_enemies if e.get("enemyId") == enemy_id), None)
        if stored is None:
            raise _YokaiNotOnStage()
        youkai_id = 0
        if idx != -1:
            youkai_id = int(mst_enemy_param.table[idx][1])
        managers.edit_dictionary(dictionary_table, youkai_id, True, False)
        managers.edit_dictionary(dictionary_diff, youkai_id, True, False)
        if i.get("dropYoukaiFlg") == 1 and youkai_id != 0 \
                and grd["rewardYoukaiId"] == 0:
            if not security.befriend_allowed(i, stored, pattern):
                metrics.incr("cheat_befriend")
                metrics.event("serious",
                              f"rejected an unearned befriend of {youkai_id}")
                log.warning("rejected befriend of %s by %s (pattern %s)",
                            youkai_id, gdkey, pattern)
                continue
            res["youkai"] = managers.yokai_won_popup(
                youkai_id, user_youkai_table, user_skill_table)
            managers.edit_dictionary(dictionary_table, youkai_id, True, True)
            managers.edit_dictionary(dictionary_diff, youkai_id, True, True)
            grd["rewardYoukaiId"] = youkai_id
            await managers.add_youkai(user_youkai_table, youkai_id,
                                      user_skill_table, user_bonus, gdkey)

    if first_clear == 1:
        for entry in level_data.get("first_reward") or []:
            val = {"itemId": entry["itemId"], "itemType": entry["itemType"],
                   "itemCnt": entry["itemCnt"], "newFlg": 0,
                   "firstRewardFlg": 1, "themeBonusFlg": 0}
            if entry["itemType"] == 1:
                managers.item_add(user_item_table, entry["itemId"], entry["itemCnt"])
            elif entry["itemType"] == 4:
                userdata.hitodama += entry["itemCnt"]
            elif entry["itemType"] == 3:
                userdata.ymoney += entry["itemCnt"]
            elif entry["itemType"] == 12:
                if player_icon_table_box[0].find_index([str(entry["itemId"])]) == -1:
                    player_icon_table_box[0] = managers.add_icon(
                        player_icon_table_box[0], int(entry["itemId"]))
                    val["newFlg"] = 1
            res["userItemResultList"].append(val)


async def game_end(request: web.Request, game_end_type: int = GAME_END) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    if not req:
        return utils.bad_request()
    if game_end_type == GAME_END:
        req["score"] = req.get("score", 0) + 10000
    req_id = await manage_data.get_ywp_user(gdkey, "ywp_user_requestid")
    if not req_id or not req.get("requestId") or req_id != req["requestId"]:
        metrics.incr("battle_invalid_session")
        return utils.encrypted_json(
            consts.msg_box_response("This session is invalid", "INVALID SESSION"))
    rejection = security.validate_battle(req, req_id)
    if rejection is not None:
        metrics.event("serious", f"rejected a battle result: {rejection}")
        log.warning("rejected battle result for %s: %s", gdkey, rejection)
        await manage_data.set_ywp_user(gdkey, "ywp_user_requestid", "")
        return utils.encrypted_json(
            consts.msg_box_response("This result could not be verified.",
                                    "Invalid result"))
    level_data_all = json.loads(game_data.gamedata_cache["stage_data"])
    stage_id = req.get("stageId", 0)
    if str(stage_id) not in level_data_all:
        return utils.bad_request()
    level_data = level_data_all[str(stage_id)]
    userdata = await YwpUserData.load(gdkey)
    if userdata is None:
        return utils.bad_request()

    youkai_diff = parser_for(YwpUserYoukai, "")
    dictionary_diff = parser_for(YwpUserDictionary, "")
    res = _game_end_response_base()
    grd = res["userGameResultData"]
    grd["score"] = req.get("score", 0)
    grd["exp"] = managers.score_to_exp(req.get("score", 0))
    grd["money"] = managers.score_to_money(req.get("score", 0))
    grd["stageId"] = stage_id

    user_item_table = parser_for(YwpUserItem, await _str_table(gdkey, "ywp_user_item"))
    ywp_user_stage = parser_for(YwpUserStage, await _str_table(gdkey, "ywp_user_stage"))
    ywp_user_map = parser_for(YwpUserMap, await _str_table(gdkey, "ywp_user_map"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    dictionary_table = parser_for(YwpUserDictionary,
                                  await _str_table(gdkey, "ywp_user_dictionary"))
    user_youkai_table = parser_for(YwpUserYoukai,
                                   await _str_table(gdkey, "ywp_user_youkai"))
    user_skill_table = parser_for(YwpUserYoukaiSkill,
                                  await _str_table(gdkey, "ywp_user_youkai_skill"))
    player_icon_box = [TableParser(await _str_table(gdkey, "ywp_user_player_icon"))]
    menufunc_table = parser_for(YwpUserMenufunc,
                                await _str_table(gdkey, "ywp_user_menufunc"))
    tutorial_list = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))

    mst_enemy_param = TableParser(_mst_table_str("ywp_mst_youkai_enemy_param"))
    for i in req.get("enemyYoukaiResultList") or []:
        idx = mst_enemy_param.find_index([str(i.get("enemyId", 0))])
        if idx != -1:
            youkai_id = int(mst_enemy_param.table[idx][1])
            managers.edit_dictionary(dictionary_table, youkai_id, True, False)
            managers.edit_dictionary(dictionary_diff, youkai_id, True, False)

    old_idx = managers.stage_get_index(ywp_user_stage, stage_id)
    old_star1 = old_star2 = old_star3 = 0
    if old_idx != -1:
        old_star1 = ywp_user_stage.items[old_idx].Star1
        old_star2 = ywp_user_stage.items[old_idx].Star2
        old_star3 = ywp_user_stage.items[old_idx].Star3

    if game_end_type == GAME_END:
        first_clear = _handle_stage(req, res, ywp_user_stage, ywp_user_map, level_data)
        try:
            user_deck = parser_for(YwpUserYoukaiDeck,
                                   await _str_table(gdkey, "ywp_user_youkai_deck"))
            await _handle_drop(req, res, dictionary_table, dictionary_diff,
                               user_youkai_table, user_skill_table, user_item_table,
                               player_icon_box, userdata, level_data, first_clear,
                               user_bonus, gdkey, user_deck)
        except _YokaiNotOnStage:
            return utils.encrypted_json(
                consts.msg_box_response("Yokai not on stage", "Error"))
        _handle_tutorial(res, tutorial_list, level_data, first_clear)
        _handle_menufunc(level_data, menufunc_table, first_clear)

    new_stars = 0
    if grd["starGetFlg1"] == 1 and old_star1 != 1:
        new_stars += 1
    if grd["starGetFlg2"] == 1 and old_star2 != 1:
        new_stars += 1
    if grd["starGetFlg3"] == 1 and old_star3 != 1:
        new_stars += 1

    await _handle_user_youkai(req, res, user_youkai_table, gdkey)

    await manage_data.set_ywp_user(gdkey, "ywp_user_requestid", "")
    await manage_data.set_ywp_user(gdkey, "ywp_user_stage", str(ywp_user_stage))
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", str(user_youkai_table))
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", str(user_item_table))
    userdata.ymoney += grd["money"]
    await userdata.save(gdkey)
    await manage_data.set_ywp_user(gdkey, "ywp_user_menufunc", str(menufunc_table))
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   tutorial_list.serialize())
    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary", str(dictionary_table))
    await manage_data.set_ywp_user(gdkey, "ywp_user_player_icon",
                                   str(player_icon_box[0]))
    await manage_data.set_ywp_user(gdkey, "ywp_user_map", str(ywp_user_map))
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                   str(user_skill_table))
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   str(user_bonus))

    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    res["ywp_user_youkai_skill"] = str(user_skill_table)
    res["ywp_user_youkai_bonus_effect_diff"] = ""
    res["ywp_user_youkai_strong_skill_diff"] = ""
    res["ywp_user_youkai"] = str(user_youkai_table)
    res["ywp_user_dictionary"] = str(dictionary_table)

    total_soult = sum(k.get("skillUseNum", 0)
                      for k in req.get("userYoukaiResultList") or [])
    user_mission = await managers.mission_update_progress(
        gdkey, MissionType.CollectTotalScore, req.get("score", 0), None, True)
    if new_stars > 0:
        user_mission = await managers.mission_update_progress(
            gdkey, MissionType.CollectTotalStars, new_stars, user_mission, True)
    await managers.mission_update_progress(
        gdkey, MissionType.DoTotalSoults, total_soult, user_mission, True)
    await managers.mission_update_progress(
        gdkey, MissionType.CreateTotalBonusBalls, req.get("bonusBlockNum", 0),
        user_mission, True)
    await managers.mission_update_progress(
        gdkey, MissionType.EnterFeverTimeTotalTimes, req.get("feverTimeNum", 0),
        user_mission, True)
    await managers.mission_update_progress(
        gdkey, MissionType.CompleteStageInSeconds, stage_id, user_mission, True,
        req.get("clearTimeSec", 0))
    await managers.mission_update_progress(
        gdkey, MissionType.PopTotalPuni, req.get("eraseNumTotal", 0),
        user_mission, True)
    await managers.save_user_mission(gdkey, user_mission)

    await utils.add_tables_to_response(consts.GAME_END_TABLES, res, True, gdkey)
    response = utils.encrypted_json(res)
    await managers.refresh_ywp_user_friend_rank(gdkey, new_stars, 0)
    metrics.incr("battles_finished")
    if grd["rewardYoukaiId"]:
        metrics.incr("yokai_befriended")
    return response


async def game_retire(request: web.Request) -> web.Response:
    return await game_end(request, GAME_RETIRE)


def _enemy_youkai_order_list() -> list[dict]:
    return [
        {"addTime": 0, "addScore": 0, "enemyYoukaiList": [
            {"actionTurn": 4, "hp": 216, "atkPower": 94, "enemyId": 536800101},
            {"actionTurn": 3, "hp": 333, "atkPower": 80, "enemyId": 536800102},
            {"actionTurn": 5, "hp": 201, "atkPower": 60, "enemyId": 536800103},
        ]},
        {"addTime": 0, "addScore": 0, "enemyYoukaiList": [
            {"actionTurn": 3, "hp": 389, "atkPower": 168, "enemyId": 536800201},
            {"actionTurn": 5, "hp": 358, "atkPower": 111, "enemyId": 536800202},
            {"actionTurn": 4, "hp": 308, "atkPower": 136, "enemyId": 536800203},
        ]},
        {"addTime": 0, "addScore": 0, "enemyYoukaiList": [
            {"actionTurn": 9, "hp": 9999999, "atkPower": 234, "enemyId": 536800301},
        ]},
    ]


def _continue_info_list() -> list[dict]:
    return [
        {"continueNum": 1, "needMoney": 300, "addTime": 5, "recoveryValue": 100000},
        {"continueNum": 2, "needMoney": 500, "addTime": 5, "recoveryValue": 100000},
    ]


def _build_user_youkai_list(deck_data: str, youkai_data: str) -> list[dict]:
    try:
        parser = TableParser(youkai_data)
        user_deck = deck_data.split('|')
        out = []
        for i in range(1, min(6, len(user_deck))):
            youkai_id = user_deck[i]
            idx = parser.find_index([youkai_id])
            if idx != -1:
                out.append({
                    "youkaiId": int(youkai_id),
                    "skillLv": 1,
                    "sSkillLv": 1,
                    "hp": int(parser.table[idx][3]),
                    "atkPower": int(parser.table[idx][4]),
                })
        return out
    except Exception as ex:
        log.warning("could not build the score attack deck: %s", ex)
        return []


async def game_start_score_attack(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    if not req:
        return utils.bad_request()
    userdata = await YwpUserData.load(gdkey)
    if userdata is None:
        return utils.bad_request()
    if userdata.hitodama > 0 or userdata.freeHitodama > 0:
        if userdata.hitodama > 0:
            userdata.hitodama -= 1
        else:
            if userdata.freeHitodama == 5:
                userdata.hitodamaRecoverSec = 900
            userdata.freeHitodama -= 1
        res = common_response_full()
        res.update({
            "itemValue": "0|0|0|0",
            "userYoukaiList": [],
            "responseCodeTeamEvent": 0,
            "ywp_user_data": userdata.to_dict(),
            "scoreLogSendFlg": 1,
            "responseCode": 0,
            "requestId": "0",
            "addHPByWatchEffect": 0,
            "addHPByGokuEffect": 0,
            "freePlayFlg": 0,
            "ymoneyShopSaleList": [5],
            "enemyYoukaiOrderList": [],
            "continueInfoList": [],
            "addAtkByGokuEffect": 0,
            "scoreAttackId": 1068,
        })
        request_id = str(int(time.time() * 1000))
        res["requestId"] = request_id
        res["scoreAttackId"] = req.get("scoreAttackId") or 1068
        res["freePlayFlg"] = req.get("freePlayFlg") or 0
        try:
            deck_data = await _str_table(gdkey, "ywp_user_youkai_deck")
            youkai_data = await _str_table(gdkey, "ywp_user_youkai")
            if deck_data and youkai_data:
                res["userYoukaiList"] = _build_user_youkai_list(deck_data, youkai_data)
            await manage_data.set_ywp_user(gdkey, "ywp_user_requestid", request_id)
            await userdata.save(gdkey)
            res["enemyYoukaiOrderList"] = _enemy_youkai_order_list()
            res["continueInfoList"] = _continue_info_list()
            tables = ["ywp_mst_bonus_block_lot", "ywp_user_event", "ywp_user_item",
                      "ywp_mst_youkai_bonus_effect_exclude", "ywp_user_dictionary",
                      "ywp_mst_score_attack_breed", "ywp_mst_big_boss",
                      "ywp_mst_score_attack_youkai_assist", "enemyYoukaiOrderList",
                      "continueInfoList", "ywp_mst_event",
                      "ywp_mst_youkai_pos_effect_exclude", "ywp_mst_big_boss_effect",
                      "ywp_mst_score_attack", "ywp_mst_game_const"]
            await utils.add_tables_to_response(tables, res, True, gdkey)
            return utils.encrypted_json(res)
        except Exception as ex:
            log.error("score attack start failed for %s: %s", gdkey, ex)
            return utils.bad_request()
    return utils.encrypted_json(consts.msg_box_response(
        "You don't have enough spirit.", "Not Enough Spirit"))


def _score_attack_result_data() -> dict:
    return {"weekHighScore": 0, "totalHighScore": 0, "rewardYoukaiId": 0,
            "itemScoreBonus": 0, "hpScoreBonus": 0, "itemScoreBonusPctg": 0,
            "scoreUpdateFlg": 0, "youkaiScoreBonus": 0, "score": 0, "money": 0,
            "leagueId": 5, "prevRank": 0, "youkaiScoreBonusPctg": 0,
            "hpScoreBonusPctg": 0, "rank": 6, "exp": 0, "groupNo": 403}


async def game_end_score_attack(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    if not req:
        return utils.bad_request()
    req_id = await manage_data.get_ywp_user(gdkey, "ywp_user_requestid")
    if not req_id or not req.get("requestId") or req_id != req["requestId"]:
        return utils.encrypted_json(
            consts.msg_box_response("This session is invalid", "INVALID SESSION"))
    userdata = await YwpUserData.load(gdkey)
    if userdata is None:
        return utils.bad_request()

    res = common_response_full()
    res.update({
        "responseCode": 0,
        "userGameResultData": _score_attack_result_data(),
        "userYoukaiResultList": [],
        "ymoneyShopSaleList": [5],
        "teamEventButtonHiddenFlg": 1,
        "responseCodeTeamEvent": 0,
    })
    grd = res["userGameResultData"]
    score = req.get("score", 0)
    grd["score"] = score
    grd["exp"] = min(score // 400, 500)
    grd["money"] = min(score // 2000, 100)

    hist_total = TableParser(await _str_table(gdkey, "ywp_user_hist_total"))
    hist_total.table[0][21] = "2025-09-18 01:16:35"
    hist_total.table[0][22] = "2258"
    total_best = int(hist_total.table[0][22])
    is_new_record = False
    if score > total_best:
        is_new_record = True
        hist_total.table[0][22] = str(score)
        hist_total.table[0][21] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_best = score
    grd["totalHighScore"] = total_best

    hist_weekly = TableParser(await _str_table(gdkey, "ywp_user_hist_puzzle_weekly"))
    weekly_best = int(hist_weekly.table[3][0])
    if score > weekly_best:
        hist_weekly.table[3][0] = str(score)
        weekly_best = score
    grd["weekHighScore"] = weekly_best

    await manage_data.set_ywp_user(gdkey, "ywp_user_hist_puzzle_weekly",
                                   str(hist_weekly))
    await manage_data.set_ywp_user(gdkey, "ywp_user_hist_total", str(hist_total))

    try:
        pending = {
            "score": score,
            "best_score": total_best,
            "timestamp": int(time.time() * 1000),
            "is_new_record": is_new_record,
            "use_current_score": is_new_record,
        }
        await manage_data.set_ywp_user(gdkey, "ywp_pending_score", pending)
        grd["scoreUpdateFlg"] = 1 if is_new_record else 0

        user_youkai_table = TableParser(await _str_table(gdkey, "ywp_user_youkai"))
        youkai_mst = TableParser(_mst_table_str("ywp_mst_youkai"))
        youkai_level_mst = TableParser(_mst_table_str("ywp_mst_youkai_level"))

        for yokai_result in req.get("userYoukaiResultList") or []:
            yid = yokai_result.get("youkaiId", 0)
            youkai_idx = user_youkai_table.find_index([str(yid)])
            if youkai_idx == -1:
                continue
            mst_idx = youkai_mst.find_index([str(yid)])
            if mst_idx == -1:
                continue
            level_type = int(youkai_mst.table[mst_idx][5])
            item = {"haveFlg": False, "isMaxLevel": False, "isLockLevel": False,
                    "before": managers.exp_info(), "youkaiId": yid,
                    "canEvolve": False, "after": managers.exp_info()}
            before, after = item["before"], item["after"]
            row = user_youkai_table.table[youkai_idx]
            before["level"] = int(row[1])
            before["exp"] = int(row[2])
            before["expBar"]["denominator"] = int(row[5])
            before["expBar"]["numerator"] = int(row[6])
            before["expBar"]["pctg"] = int(row[7])

            exp_gain = min(yokai_result.get("damageTotal", 0) // 10, 200)
            after["exp"] = before["exp"] + exp_gain

            new_level = before["level"]
            index = 1
            level_found = False
            while not level_found:
                level_index = -1
                for tmp_idx, lrow in enumerate(youkai_level_mst.table):
                    if lrow[0] == str(level_type) and lrow[1] == str(index):
                        level_index = tmp_idx
                        break
                if level_index != -1:
                    min_exp = int(youkai_level_mst.table[level_index][2])
                    max_exp = int(youkai_level_mst.table[level_index][3])
                    if min_exp <= after["exp"] <= max_exp:
                        new_level = int(youkai_level_mst.table[level_index][1])
                        after["expBar"]["denominator"] = (max_exp + 1) - min_exp
                        after["expBar"]["numerator"] = after["exp"] - min_exp
                        after["expBar"]["pctg"] = int(
                            (after["expBar"]["numerator"] /
                             after["expBar"]["denominator"]) * 100)
                        level_found = True
                    index += 1
                else:
                    item["isMaxLevel"] = True
                    level_found = True
            after["level"] = new_level

            row[1] = str(after["level"])
            row[2] = str(after["exp"])
            row[5] = str(after["expBar"]["denominator"])
            row[6] = str(after["expBar"]["numerator"])
            row[7] = str(after["expBar"]["pctg"])
            res["userYoukaiResultList"].append(item)

        userdata.ymoney += int(grd["money"])
        await manage_data.set_ywp_user(gdkey, "ywp_user_requestid", "")
        await manage_data.set_ywp_user(gdkey, "ywp_user_youkai",
                                       str(user_youkai_table))
        await userdata.save(gdkey)
        try:
            await manage_data.set_ywp_user(gdkey, f"sa_continues_{req['requestId']}", 0)
        except Exception:
            pass

        tables = ["ywp_user_youkai", "ywp_user_tutorial_list",
                  "ywp_user_youkai_bonus_effect", "ywp_user_event",
                  "ywp_user_hist_youkai_daily", "ywp_user_youkai_strong_skill",
                  "ywp_user_hist_youkai_total", "ywp_user_hist_puzzle_weekly",
                  "ywp_user_league_rank", "ywp_user_dictionary", "ywp_user_map",
                  "ywp_user_hist_total", "ywp_user_self_rank",
                  "ywp_user_hist_puzzle_daily", "ywp_user_stage_relation_progress",
                  "ywp_user_youkai_skill", "ywp_user_icon_budge", "ywp_mst_event",
                  "ywp_user_stage", "ywp_user_steal_progress", "ywp_user_data",
                  "ywp_user_score_attack_reward", "ywp_user_shop_item_unlock",
                  "ywp_user_event_ranking_reward", "ywp_user_friend_star_rank",
                  "ywp_user_friend_rank"]
        await utils.add_tables_to_response(tables, res, True, gdkey)
        log.info("score attack finished for %s: score %d (best %d, record %s)",
                 gdkey, score, total_best, is_new_record)
        return utils.encrypted_json(res)
    except Exception as ex:
        log.error("score attack end failed for %s: %s", gdkey, ex, exc_info=True)
        return utils.bad_request()
