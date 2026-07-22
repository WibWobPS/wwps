from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from aiohttp import web

from .. import config, consts, game_data, logging_setup, managers, metrics, utils
from .. import user_data as manage_data
from ..dto import TutorialList, common_response_dict, common_response_full
from ..rows import (YwpUserItem, YwpUserMap, YwpUserYoukai,
                    YwpUserYoukaiBonusEffect, YwpUserYoukaiSkill,
                    YwpUserDictionary, parser_for)
from ..table_parser import TableParser
from ..ywp_user_data import YwpUserData

log = logging_setup.get(__name__)

_unmarshal_cache: dict[str, object] = {}


async def login(request: web.Request) -> web.Response:
    from .misc import can_do_shrine_today
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("gdkeyValue")
    acc = await manage_data.get_account_from_gdkey(gdkey)

    if await can_do_shrine_today(gdkey):
        await manage_data.set_ywp_user(gdkey, "ywp_user_addition", False)
    await managers.check_shop_limit_reset(gdkey)

    maps_to_add = json.loads(game_data.gamedata_cache["maps_to_add_login"])
    raw_map = await manage_data.get_ywp_user(gdkey, "ywp_user_map")
    user_map = parser_for(YwpUserMap, raw_map if isinstance(raw_map, str) else None)
    for map_id in maps_to_add:
        if not any(x.MapId == map_id for x in user_map.items):
            user_map.items.append(YwpUserMap(MapId=map_id, IsUnlocked=1, FriendCount=0))
    await manage_data.set_ywp_user(gdkey, "ywp_user_map", str(user_map))

    resdict = common_response_dict()
    await utils.add_tables_to_response(consts.LOGIN_TABLES_PUNI, resdict, True, gdkey)
    resdict["ywp_user_map"] = str(user_map)
    acc.last_login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    metrics.incr("logins")
    log.info("login %s", gdkey)
    return utils.encrypted_json(resdict)


async def _create_user_youkai_save(gdkey: str):
    yokai = parser_for(YwpUserYoukai, "")
    skill = parser_for(YwpUserYoukaiSkill, "")
    bonus = parser_for(YwpUserYoukaiBonusEffect, "")
    for yid in (2157000, 2213000, 2231000, 2235000, 2281000):
        await managers.add_youkai(yokai, yid, skill, bonus, gdkey)
    return str(yokai), str(skill), str(bonus)


async def _create_save(tables: dict, userdata: YwpUserData, gdkey: str):
    tables["ywp_user_data"] = userdata.to_dict()

    for name in ("ywp_user_youkai_collect", "ywp_user_youkai_intro",
                 "ywp_user_goku_youkai_intro_release", "ywp_user_goku_story",
                 "ywp_user_friend_request_recv", "ywp_user_friend",
                 "ywp_user_present_box_list", "ywp_user_crystal_menu",
                 "ywp_user_drive_progress", "ywp_user_event_point",
                 "ywp_user_event_point_trade", "ywp_user_event_ranking_reward",
                 "ywp_user_event_tutorial", "ywp_user_friend_stage",
                 "ywp_user_medal_point_trade", "ywp_user_mini_game_map",
                 "ywp_user_mini_game_map_friend", "ywp_user_raid_boss",
                 "ywp_user_score_attack_reward", "ywp_user_stage_rank",
                 "ywp_user_stage_relation_progress", "ywp_user_steal_progress"):
        tables[name] = []
    if config.is_wibwob:
        tables["ywp_user_gacha"] = [{"gachaType": 3, "feverPctg": 0}]
    else:
        tables["ywp_user_gacha"] = []
    tables["ywp_user_league_rank"] = None

    for name in ("ywp_user_gacha_stamp", "ywp_user_youkai_strong_skill",
                 "ywp_user_youkai_legend_release_history",
                 "ywp_user_treasure_series", "ywp_user_treasure",
                 "ywp_user_shop_item_unlock", "ywp_user_item",
                 "ywp_user_event_progress", "ywp_user_conflate"):
        tables[name] = None

    self_rank = {
        "iconId": userdata.iconId, "playerName": userdata.playerName,
        "titleId": userdata.titleId, "getStar": 0, "userId": userdata.userId,
        "dicCnt": 0, "score": 0, "youkaiId": userdata.youkaiId,
        "getStarModiDt": None, "hitodamaSendFlg": 1, "onedariSendFlg": 1,
        "rank": 1, "self": 1,
    }
    tables["ywp_user_friend_star_rank"] = [self_rank]
    tables["ywp_user_friend_rank"] = [self_rank]
    tables["ywp_user_friend_dictionary_rank"] = [self_rank]
    tables["ywp_user_self_rank"] = {
        "rankStart": 1, "score": 0, "leagueId": 5, "rank": 0, "groupNo": 0,
        "remainSec": 0, "leagueChangeStatus": 0, "userId": userdata.userId}
    tables["login_stamp"] = "0|0|0"
    tables["ywp_user_youkai_medal_cnt"] = "0"
    tables["ywp_user_player_plate"] = "1"
    tables["ywp_user_player_effect"] = "1"
    tables["ywp_user_player_codename"] = "1"

    yk, sk, bn = await _create_user_youkai_save(gdkey)
    tables["ywp_user_youkai"] = yk
    tables["ywp_user_youkai_skill"] = sk
    tables["ywp_user_youkai_bonus_effect"] = bn


async def _register_default_tables(gdkey: str, userdata: YwpUserData):
    tables: dict = {}
    await _create_save(tables, userdata, gdkey)
    tables["opening_tutorial_flg"] = False
    for user_table in consts.LOGIN_TABLES_PUNI:
        if "ywp_user" not in user_table or user_table == "ywp_user_data":
            continue
        if user_table in tables:
            continue
        data = game_data.gamedata_cache.get(user_table + "_def")
        if data is not None:
            try:
                tables[user_table] = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                tables[user_table] = data
        else:
            raise Exception(f"Missing default table {user_table}_def")
    await manage_data.set_entire_user_data(gdkey, tables)


async def create_user(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    acc = await manage_data.get_account_from_gdkey(gdkey)
    icon_id = req.get("iconID", 1)
    title = 1 if config.is_wibwob else icon_id
    userdata = YwpUserData(icon_id=icon_id, title_id=title,
                           player_name=req.get("playerName", ""))
    acc.start_date = int(time.time() * 1000)
    userdata.characterId = acc.character_id
    userdata.userId = acc.user_id
    acc.is_dirty = True
    await manage_data.update_account(acc)
    try:
        await _register_default_tables(gdkey, userdata)
    except Exception:
        log.error("could not register default tables for %s", gdkey, exc_info=True)
        return web.Response(status=500, text="Internal server error")
    res = common_response_full()
    res["rewardList"] = []
    res["ywp_user_tutorial_list"] = game_data.gamedata_cache["ywp_user_tutorial_list_def"]
    res["ywp_user_data"] = userdata.to_dict()
    metrics.incr("accounts_created")
    metrics.event("good", f"new player {userdata.playerName}")
    log.info("created account %s for %s", acc.character_id, userdata.playerName)
    return utils.encrypted_json(res)


def _base_master_data() -> dict:
    return {
        "serverDt": int(time.time() * 1000),
        "resultType": 0,
        "shopSaleList": game_data.deserialize_gamedata("shopSaleList"),
        "dialogTitle": "",
        "resultCode": 0,
        "hitodamaShopSaleList": game_data.deserialize_gamedata("hitodamaShopSaleList"),
        "ywpToken": "",
        "token": None,
        "storeUrl": "",
        "webServerIp": "",
        "mstVersionMaster": int(game_data.gamedata_cache["mstVersionMaster"]),
        "nextScreenType": 0,
        "ymoneyShopSaleList": game_data.deserialize_gamedata("ymoneyShopSaleList"),
        "dialogMsg": "",
    }


def _unmarshal_or_cache(name: str, raw: str):
    if name not in _unmarshal_cache:
        try:
            _unmarshal_cache[name] = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            _unmarshal_cache[name] = raw
    return _unmarshal_cache[name]


async def get_master(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    master = _base_master_data()
    if "tableNames" not in req:
        return utils.bad_request()
    tbl_names = req["tableNames"]
    if tbl_names != "all":
        tables = tbl_names.split('|')
    else:
        tables = consts.ALL_TABLE.split('|')
    for name in tables:
        if name in game_data.gamedata_cache:
            master[name] = _unmarshal_or_cache(name, game_data.gamedata_cache[name])
        else:
            log.warning("getMaster: unknown table %s", name)
    return utils.encrypted_json(master)


async def get_l5id_status(request: web.Request) -> web.Response:
    res = common_response_full()
    res["L5IdStatus"] = {"code": 1, "name": "???????????????", "point": 0}
    res["beforeCode"] = 1
    res["afterCode"] = 1
    res["isChanged"] = False
    res["maxCode"] = 1
    return utils.encrypted_json(res)


async def _udkey_player_item(gdkey: str) -> dict | None:
    userdata = await YwpUserData.load(gdkey)
    if userdata is None:
        return None
    account = await manage_data.get_account_from_gdkey(gdkey)
    start = datetime.fromtimestamp(account.start_date / 1000, tz=timezone.utc)
    return {
        "iconId": userdata.iconId,
        "playerName": userdata.playerName,
        "youkaiId": userdata.youkaiId,
        "lastUpdateDate": account.last_login_time,
        "titleId": userdata.titleId,
        "gdkey": gdkey,
        "userId": userdata.userId,
        "playStartDate": start.strftime("%Y-%m-%d %H:%M:%S"),
    }


async def get_gdkey_accounts(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkeys = []
    for gdkey_dict in req.get("gdkeys") or []:
        gdkeys.extend(gdkey_dict.values())
    udkey = req.get("deviceID", "")
    player_items = []
    for gdkey in gdkeys:
        try:
            item = await _udkey_player_item(gdkey)
        except Exception:
            item = None
        if item is None:
            await manage_data.delete_user(udkey, gdkey)
            continue
        player_items.append(item)
    res = common_response_full()
    res["udkeyPlayerList"] = player_items
    return utils.encrypted_json(res)


async def delete_user(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    if req.get("characterID") == userdata.characterId:
        resp_code = 0
        if req.get("finalAnswerFlg") == 1:
            await manage_data.delete_user(req.get("deviceID"), gdkey)
    else:
        resp_code = 1
    res = common_response_full()
    res["responseCode"] = resp_code
    return utils.encrypted_json(res)


async def user_info_refresh(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    try:
        userdata = await YwpUserData.load(gdkey)
        resdict = {
            "ShopSaleList": None,
            "ServerDate": int(time.time() * 1000),
            "YwpToken": "",
            "YMoneyShopSaleList": game_data.deserialize_gamedata("ymoneyShopSaleList"),
            "MstVersionMaster": int(game_data.gamedata_cache["mstVersionMaster"]),
            "ResultCode": 0,
            "NextScreenType": 0,
            "HitodamaShopSaleList": None,
            "UserData": userdata.to_dict(),
            "ResultType": 0,
        }
        for item in req.get("requireInfoList") or []:
            try:
                resdict[item] = await manage_data.get_ywp_user(gdkey, item)
            except Exception as ex:
                log.warning("userInfoRefresh: table %s failed: %s", item, ex)
        return utils.encrypted_json(resdict)
    except Exception:
        return utils.encrypted_json(
            consts.msg_box_response("This account doesn't exist",
                                    "Authentication Error"))


async def rename(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    new_name = req.get("newPlayerName")
    if userdata is not None and new_name:
        userdata.playerName = new_name
    await managers.refresh_ywp_user_friend(gdkey, -1, -1, userdata.playerName, -1, "")
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    response = utils.encrypted_json(res)
    await userdata.save(gdkey)
    return response


async def update_profile(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)

    raw_icon = await manage_data.get_ywp_user(gdkey, "ywp_user_player_icon")
    user_player_icon = TableParser(raw_icon if isinstance(raw_icon, str) else None)
    user_player_title = await manage_data.get_ywp_user(gdkey, "ywp_user_player_title")
    user_player_plate = await manage_data.get_ywp_user(gdkey, "ywp_user_player_plate")
    user_player_effect = await manage_data.get_ywp_user(gdkey, "ywp_user_player_effect")
    user_player_codename = await manage_data.get_ywp_user(gdkey, "ywp_user_player_codename")

    if req.get("iconID", 0) > 0:
        if user_player_icon.find_index([str(req["iconID"])]) != -1:
            userdata.iconId = req["iconID"]
        else:
            return utils.encrypted_json(consts.msg_box_response("Error", "Error"))
    if req.get("titleID", 0) > 0:
        userdata.titleId = req["titleID"]
    if req.get("codenameId", 0) > 0:
        userdata.codenameId = req["codenameId"]
    if req.get("effectId", 0) > 0:
        userdata.effectId = req["effectId"]
    if req.get("plateId", 0) > 0:
        userdata.plateId = req["plateId"]
    await userdata.save(gdkey)
    res = common_response_full()
    res["ywp_user_player_icon"] = str(user_player_icon)
    res["ywp_user_player_title"] = user_player_title
    res["ywp_user_player_plate"] = user_player_plate
    res["ywp_user_player_codename"] = user_player_codename
    res["ywp_user_player_effect"] = user_player_effect
    res["ywp_user_data"] = userdata.to_dict()
    response = utils.encrypted_json(res)
    await managers.refresh_ywp_user_friend(gdkey, userdata.titleId,
                                           userdata.iconId, "", -1, "")
    return response


async def update_tutorial_flag(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    tutorial_list = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))
    tutorial_list.edit_tutorial_flg(req.get("tutorialType", 0),
                                    req.get("tutorialId", 0),
                                    req.get("tutorialStatus", 0))
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   tutorial_list.serialize())
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_tutorial_list"] = tutorial_list.serialize()
    res["ywp_user_data"] = userdata.to_dict()
    return utils.encrypted_json(res)


_mst_conflate = None


def _get_mst_conflate():
    global _mst_conflate
    if _mst_conflate is None:
        from ..rows import YwpMstConflate
        raw = json.loads(game_data.gamedata_cache["ywp_mst_conflate"])["tableData"]
        _mst_conflate = parser_for(YwpMstConflate, raw)
    return _mst_conflate


def _check_fusion_object(reward_type: int, obj_id: int, user_yokai, user_item) -> bool:
    if reward_type == managers.RewardType.Yokai:
        return managers.get_youkai_index(user_yokai, obj_id) != -1
    if reward_type == managers.RewardType.Item:
        return user_item.find_index([str(obj_id)]) != -1
    return False


def _apply_fusion_object(reward_type: int, obj_id: int, user_yokai, user_skill,
                         user_item, user_dict, user_bonus):
    if reward_type == managers.RewardType.Yokai:
        managers.delete_youkai(user_yokai, user_skill, obj_id, user_bonus)
        managers.edit_dictionary(user_dict, obj_id, True, False)
    elif reward_type == managers.RewardType.Item:
        managers.item_remove(user_item, obj_id, 1)
    else:
        raise NotImplementedError("Unknown reward type for fuse objects")


async def _get_str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


async def conflate(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    user_yokai = parser_for(YwpUserYoukai, await _get_str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _get_str_table(gdkey, "ywp_user_youkai_skill"))
    user_item = parser_for(YwpUserItem, await _get_str_table(gdkey, "ywp_user_item"))
    user_dict = parser_for(YwpUserDictionary,
                           await _get_str_table(gdkey, "ywp_user_dictionary"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _get_str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    userdata = await YwpUserData.load(gdkey)

    mst_item = next((x for x in _get_mst_conflate().items
                     if x.ConflateID == req.get("conflateId")), None)
    if mst_item is None:
        return web.Response(text=json.dumps(
            consts.msg_box_response("Invalid conflate", "Err")))
    if userdata.ymoney < mst_item.YMoneyCost:
        return web.Response(text=json.dumps(
            consts.msg_box_response("Not enough Y-Money", "Err")))
    try:
        if not (_check_fusion_object(mst_item.FuseObject1Type, mst_item.FuseObject1ID,
                                     user_yokai, user_item)
                and _check_fusion_object(mst_item.FuseObject2Type,
                                         mst_item.FuseObject2ID, user_yokai, user_item)):
            raise ValueError("Missing fusion components")
        _apply_fusion_object(mst_item.FuseObject1Type, mst_item.FuseObject1ID,
                             user_yokai, user_skill, user_item, user_dict, user_bonus)
        _apply_fusion_object(mst_item.FuseObject2Type, mst_item.FuseObject2ID,
                             user_yokai, user_skill, user_item, user_dict, user_bonus)
    except (ValueError, NotImplementedError) as ex:
        return utils.encrypted_json(consts.msg_box_response(str(ex), "Err"))

    userdata.ymoney -= mst_item.YMoneyCost
    res = common_response_full()
    res["youkai"] = managers.yokai_won_popup(mst_item.ResultID, user_yokai, user_skill)
    await managers.add_youkai(user_yokai, mst_item.ResultID, user_skill, user_bonus, gdkey)
    managers.edit_dictionary(user_dict, mst_item.ResultID, True, True)

    res["ywp_user_youkai"] = str(user_yokai)
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    res["ywp_user_youkai_skill"] = str(user_skill)
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill", res["ywp_user_youkai_skill"])
    res["ywp_user_dictionary"] = str(user_dict)
    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary", res["ywp_user_dictionary"])
    res["ywp_user_item"] = str(user_item)
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    await manage_data.set_ywp_user(gdkey, "ywp_user_item", res["ywp_user_item"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_data", userdata.to_dict())
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   res["ywp_user_youkai_bonus_effect"])
    res["ywp_user_icon_budge"] = await _get_str_table(gdkey, "ywp_user_icon_budge")
    res["ywp_user_youkai_deck"] = await _get_str_table(gdkey, "ywp_user_youkai_deck")
    res["ywp_user_menufunc"] = await _get_str_table(gdkey, "ywp_user_menufunc")
    await managers.mission_update_progress(gdkey, managers.MissionType.FuseTotalYokai, 1)
    return utils.encrypted_json(res)
