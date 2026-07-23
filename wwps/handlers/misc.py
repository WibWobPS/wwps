from __future__ import annotations

import json
import random
import time
from datetime import datetime

from aiohttp import web

from .. import auth, config, consts, game_data, managers, utils
from .. import user_data as manage_data
from ..dto import common_response_full
from ..ywp_user_data import YwpUserData
from .. import logging_setup, metrics

log = logging_setup.get(__name__)

from .init import init_collect_menu


async def _str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y%m%d")


async def can_do_shrine_today(gdkey: str) -> bool:
    last = await manage_data.get_ywp_user(gdkey, "lastAdditionDate")
    return last != _today_str()


async def mark_shrine(gdkey: str):
    await manage_data.set_ywp_user(gdkey, "lastAdditionDate", _today_str())


async def use_addition(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["responseCode"] = 0
    res["responseDetailCode"] = 0

    if await can_do_shrine_today(gdkey):
        if random.randrange(10) == 0:
            res["responseCode"] = 0
            res["responseDetailCode"] = 0
            await manage_data.set_ywp_user(gdkey, "ywp_user_addition", True)
        else:
            res["responseCode"] = 0
            res["responseDetailCode"] = 1
        await mark_shrine(gdkey)
    else:
        res["responseCode"] = 1
        res["responseDetailCode"] = 1
    return utils.encrypted_json(res)


async def init_watch(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["ywp_user_watch"] = await manage_data.get_ywp_user(gdkey, "ywp_user_watch")
    return utils.encrypted_json(res)


async def update_watch_read_flg(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    watch_id = req.get("watchId")
    user_watch = await manage_data.get_ywp_user(gdkey, "ywp_user_watch") or []
    watch_item = next((x for x in user_watch if x.get("watchId") == watch_id), None)
    if watch_item is None:
        return utils.encrypted_json(
            consts.msg_box_response("Watch not found", "Error"))
    watch_item["readFlg"] = 1
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["ywp_user_watch"] = user_watch
    await manage_data.set_ywp_user(gdkey, "ywp_user_watch", user_watch)
    return utils.encrypted_json(res)


async def update_goku_story(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    story_id = req.get("gokuStoryId", 0)
    userdata = await YwpUserData.load(gdkey)
    res = common_response_full()
    res["ywp_user_icon_budge"] = await _str_table(gdkey, "ywp_user_icon_budge")
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    stories = await manage_data.get_ywp_user(gdkey, "ywp_user_goku_story") or []
    if not any(e.get("gokuStoryId") == story_id for e in stories):
        stories.append({"gokuStoryId": story_id})
    res["ywp_user_goku_story"] = stories
    await manage_data.set_ywp_user(gdkey, "ywp_user_goku_story", stories)
    return utils.encrypted_json(res)


def _placeholder_user_data(limit_remain: int, recover_sec: int) -> dict:
    return {
        "birthday": "", "freeHitodama": 3, "friendMaxCnt": 10, "plateId": 1,
        "medalPoint": 0, "nowStageId": 1001006, "titleId": 1, "gokuCollectCnt": 0,
        "ymoney": 3285, "reviewFlg": 0, "moveReason": 0, "chargeYmoney": 0,
        "effectId": 1, "crystalCollectCnt": 0, "eventPointUpItemId": 0,
        "characterId": "3qjiw6vi", "iconId": 1,
        "limitTimeSaleRemainSec": limit_remain, "totMedalPoint": 0,
        "eventPointUpItemRemainSec": 0, "playerName": "superog",
        "todaysRemainSec": limit_remain + 1, "weeklyFreeFlg": 1, "hitodama": 0,
        "lastRenameDt": 0, "codenameId": 1, "usingItemList": [],
        "hitodamaRecoverSec": recover_sec,
        "limitTimeSaleEndDt": "2025-09-15 23:59:59", "equipWatchId": 10101,
    }


async def update_goku_menu(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    device_id = req.get("deviceId")
    goku_menu_id = req.get("gokuMenuId", 0)

    jo = {
        "shopSaleList": [], "ywpToken": "", "ymoneyShopSaleList": [],
        "mstVersionMaster": 16774, "resultCode": 0,
        "ywp_user_icon_budge": "9000|5*5|1*2000|0*10|1*2007|1*2008|1*2009|1*2010|0*9004|21*9003|0*9007|0*9008|0*9009|0*10959|0*20959|0",
        "nextScreenType": 0, "dialogMsg": "", "hitodamaShopSaleList": [],
        "webServerIp": "", "storeUrl": "", "dialogTitle": "", "resultType": 0,
        "serverDt": int(time.time() * 1000),
        "ywp_user_data": _placeholder_user_data(63646, 106),
    }

    gdkey = None
    try:
        if device_id:
            gdkeys = await manage_data.get_gdkeys_from_udkey(device_id)
            if gdkeys:
                gdkey = gdkeys[0]
                tables = await manage_data.get_entire_user_data(gdkey)
                if tables is not None and "ywp_user_data" in tables:
                    jo["ywp_user_data"] = tables["ywp_user_data"]
    except Exception as ex:
        log.warning("goku menu: could not load user data: %s", ex)

    user_menu = []
    if goku_menu_id > 0:
        user_menu.append({"gokuMenuId": goku_menu_id})
    try:
        if gdkey:
            existing = await manage_data.get_ywp_user(gdkey, "ywp_user_goku_menu")
            if existing is not None:
                user_menu = existing
                if goku_menu_id > 0 and not any(
                        x.get("gokuMenuId") == goku_menu_id for x in user_menu):
                    user_menu.append({"gokuMenuId": goku_menu_id})
            await manage_data.set_ywp_user(gdkey, "ywp_user_goku_menu", user_menu)
    except Exception as ex:
        log.warning("goku menu: could not persist menu: %s", ex)
    jo["ywp_user_goku_menu"] = user_menu

    intro_release = []
    try:
        if gdkey:
            existing = await manage_data.get_ywp_user(
                gdkey, "ywp_user_goku_youkai_intro_release")
            if existing is not None:
                intro_release = existing
            if goku_menu_id > 0:
                intro_id = goku_menu_id * 1000 + 1
                if not any(x.get("introReleaseId") == intro_id
                           for x in intro_release):
                    intro_release.append({
                        "introReleaseId": intro_id,
                        "userId": req.get("userId") or "",
                        "clearFlg": 1, "readFlg": 0, "missionType": 1,
                        "nowValue": 0, "targetValue": 0, "update": False,
                        "updateClearFlg": 0, "updateNowValue": 0,
                        "updateReadFlg": 0, "createRecord": False,
                    })
                await manage_data.set_ywp_user(
                    gdkey, "ywp_user_goku_youkai_intro_release", intro_release)
    except Exception as ex:
        log.warning("goku menu: could not persist intro release: %s", ex)
    jo["ywp_user_goku_youkai_intro_release"] = intro_release
    return utils.encrypted_json(jo)


async def update_crystal_menu(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    crystal_menu = []
    if req.get("crystalMenuId") is not None:
        crystal_menu.append({"crystalMenuId": req["crystalMenuId"]})
    jo = {
        "shopSaleList": [], "ywpToken": "", "ymoneyShopSaleList": [],
        "mstVersionMaster": 16774, "resultCode": 0, "ywp_user_icon_budge": "",
        "nextScreenType": 0, "dialogMsg": "", "hitodamaShopSaleList": [],
        "webServerIp": "", "storeUrl": "", "dialogTitle": "", "resultType": 0,
        "serverDt": int(time.time() * 1000),
        "ywp_user_data": {
            "playerName": "random", "iconId": 1,
            "userId": req.get("userId") or "0",
            "characterId": req.get("level5UserId") or "",
        },
        "ywp_user_crystal_menu": crystal_menu,
    }
    return utils.encrypted_json(jo)


async def update_collect_menu(request: web.Request) -> web.Response:
    return await init_collect_menu(request)


async def get_present_box(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    res = common_response_full()
    tables = ["ywp_user_data", "ywp_user_present_box_list", "ywp_user_icon_budge"]
    await utils.add_tables_to_response(tables, res, False, gdkey or "")
    return utils.encrypted_json(res)


async def get_ranking(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    rank_type = req.get("rankType", 0)
    res = common_response_full()
    res["rankType"] = rank_type
    res["responseCode"] = 0
    tables = ["ywp_user_data", "ywp_user_icon_budge",
              "ywp_user_score_attack_reward", "ywp_user_self_rank"]
    res["ywp_mst_score_attack_league"] = json.loads(
        game_data.gamedata_cache["ywp_mst_score_attack_league"])["data"]
    tables.append("ywp_mst_score_attack_league")
    if rank_type == 3:
        tables.append("ywp_user_friend_star_rank")
    elif rank_type == 4:
        tables += ["ywp_user_friend_star_rank", "ywp_user_friend_rank",
                   "ywp_user_league_rank"]
    elif rank_type == 5:
        tables.append("ywp_user_friend_dictionary_rank")
    elif rank_type == 8:
        tables.append("ywp_user_all_rank")
    else:
        tables += ["ywp_user_all_rank", "ywp_user_friend_dictionary_rank",
                   "ywp_user_friend_star_rank", "ywp_user_friend_rank",
                   "ywp_user_league_rank"]
    await utils.add_tables_to_response(tables, res, False, gdkey or "")
    return utils.encrypted_json(res)


async def user_stage_ranking(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    stage_id = req.get("stageID")
    stage_rank = await manage_data.get_ywp_user(gdkey, "ywp_user_stage_rank")
    new_list = []
    if stage_rank is not None:
        for element in stage_rank:
            if element.get("stageId") == stage_id:
                new_list.append(element)
    else:
        stage_rank = []
    if not new_list:
        new_entry = {"list": [], "stageId": stage_id}
        new_list.append(new_entry)
        stage_rank.append(new_entry)
        await manage_data.set_ywp_user(gdkey, "ywp_user_stage_rank", stage_rank)
    res = common_response_full()
    res["ywp_user_stage_rank"] = new_list
    return utils.encrypted_json(res)


async def serial_confirm(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    serial_code = (req.get("serialCode") or "").strip()
    try:
        code = int(serial_code)
    except ValueError:
        return utils.encrypted_json(consts.msg_box_response(
            "Invalid code. Needs to be all numbers", "Error"))

    val = auth.code_cache.get(code)
    if val is None:
        return utils.encrypted_json(consts.msg_box_response(
            "Invalid or expired code", "Error"))
    email, is_link, udkey, _expires = val
    if udkey != req.get("deviceId"):
        return utils.encrypted_json(
            consts.msg_box_response("It's not your account", "Error"))
    if is_link:
        auth.code_cache.pop(code, None)
        await manage_data.add_or_edit_email(email, udkey)
        return utils.encrypted_json(consts.msg_box_response(
            "Saves successfully linked to email.", "Success"))
    auth.code_cache.pop(code, None)
    linked = await manage_data.get_data_by_mail(email)
    if linked is None:
        return utils.encrypted_json(consts.msg_box_response(
            "No data is linked for this email", "Error"))
    old_udkey = linked["currentUdkey"]
    if old_udkey == udkey:
        return utils.encrypted_json(consts.msg_box_response(
            "You cannot transfer data\nto the same device.", "Error"))
    await manage_data.transfer_gdkeys(old_udkey, udkey)
    await manage_data.add_or_edit_email(email, udkey)
    return utils.encrypted_json(consts.msg_box_response(
        "Connected to cloud save on this\ndevice.Please restart your game.", "Error"))


async def age_confirm(request: web.Request) -> web.Response:
    return utils.encrypted_json(consts.msg_box_response(
        "WibWobPS does not support\npaid content.", "Support NHN"))


async def get_limit_hitodama(request: web.Request) -> web.Response:
    return utils.encrypted_json("{}")


async def default_handler(request: web.Request) -> web.Response:
    try:
        log.warning("unimplemented request: %s %s", request.method, request.path)
        metrics.incr("unimplemented_requests")
        msg = f"Unimplemented request:\n{request.path}"
        return utils.encrypted_json(
            consts.msg_box_response(msg, config.server_name or "WibWobPS"))
    except Exception:
        return web.Response(status=500, text="Internal server error")


async def help_inquiry_top(request: web.Request) -> web.Response:
    import os
    path = os.path.join(config.DATA_DOWNLOAD_DIR, "help.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    params = {
        "userId": request.query.get("userId", ""),
        "appVer": request.query.get("appVer", ""),
        "sdkVer": request.query.get("sdkVer", ""),
    }
    inject = (f"<script>\nwindow.__PARAMS__ = {json.dumps(params)};\n</script>")
    return web.Response(text=inject + html, content_type="text/html",
                        charset="utf-8")
