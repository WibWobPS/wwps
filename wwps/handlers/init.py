from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from aiohttp import web

from .. import config, consts, game_data, logging_setup, managers, metrics, utils
from . import launching
from .. import user_data as manage_data
from ..dto import common_response_full
from ..table_parser import TableParser
from ..ywp_user_data import YwpUserData
from .. import logging_setup, metrics

log = logging_setup.get(__name__)


async def init(request: web.Request) -> web.Response:
    try:
        body = (await request.read()).decode("utf-8")
        from .. import nhn_crypt
        decrypted = nhn_crypt.decrypt_request(body)
        req = json.loads(decrypted)
    except Exception:
        return utils.bad_request()
    if not isinstance(req, dict) or "appVer" not in req:
        return utils.bad_request()
    logging_setup.get(__name__).info("init from appVer=%s (server expects %s)",
                                     req.get("appVer"), config.game_version)
    if req["appVer"] != config.game_version:
        metrics.incr("version_mismatch")
        return utils.encrypted_json(consts.msg_box_response(
            "Game version is not\ncompatible with the server.", config.server_name))
    res = common_response_full()
    res["ywp_mst_version_master"] = game_data.gamedata_cache["ywp_mst_version_master"]
    res["gameServerUrl"] = launching._public_base(request)
    res["isEnableSerialCode"] = 1
    res["apkey"] = ""
    img = config.data_download_url
    if not (img and img.startswith("http")):
        img = launching._public_base(request) + "/dd"
    res["imgServer"] = img
    res["dispNoticeFlag"] = 2
    res["noticePageList"] = game_data.deserialize_gamedata("noticePageList")
    res["l5idUrl"] = "l5id"
    res["isAppleTrial"] = False
    res["isEnableFriendInvite"] = 1
    res["masterReacquisitionHour"] = 2
    res["isEnableYoukaiMedal"] = 1
    res["isEnableL5ID"] = 0
    res["threeKingdomTeamEventButtonHiddenFlg"] = 1
    res["teamEventButtonHiddenFlg"] = 1
    return utils.encrypted_json(res)


async def init_billing(request: web.Request) -> web.Response:
    return utils.encrypted_json(consts.msg_box_response(
        "WibWobPS does not support\npaid content. It is a non-profit,\n"
        "open source project.", "Support NHN."))


async def init_gacha_puni(request: web.Request) -> web.Response:
    await utils.read_decrypted_request(request)
    res = common_response_full()
    for key in ("ywp_user_event", "ywp_mst_youkai_bonus_effect_exclude",
                "gachaStampIdList", "ywp_mst_event_group_assist_disp",
                "canPossessionItemList", "ywp_user_gacha_stamp", "ywp_mst_event",
                "ywp_user_icon_budge", "ywp_user_gacha",
                "ywp_mst_event_youkai_assist_disp", "gachaLotRuleList",
                "ywp_mst_gacha_convert_item", "ywp_user_data",
                "ywp_mst_youkai_pos_effect_exclude", "canUseMultiGachaCoinIdList",
                "ywp_mst_coin_purchase_master", "bannerResourceList"):
        res[key] = None
    res["ywp_mst_gacha"] = json.loads(
        game_data.gamedata_cache["ywp_mst_gacha"])["tableData"]
    res["ywp_mst_item"] = json.loads(
        game_data.gamedata_cache["ywp_mst_item"])["tableData"]
    if "gachaStampList" in game_data.gamedata_cache:
        res["gachaStampList"] = json.loads(game_data.gamedata_cache["gachaStampList"])
    else:
        res["gachaStampList"] = []
    return utils.encrypted_json(res)


async def init_gacha_wibwob(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    res = common_response_full()
    res["oldDataFlg"] = 0
    res["gachaAppVerAlert"] = ""
    res["bannerResourceName"] = "gg002"
    res["ywp_mst_gacha"] = json.loads(
        game_data.gamedata_cache["ywp_mst_gacha"])["tableData"]
    res["ywp_user_icon_budge"] = await manage_data.get_ywp_user(gdkey, "ywp_user_icon_budge")
    res["ywp_user_gacha"] = await manage_data.get_ywp_user(gdkey, "ywp_user_gacha")
    return utils.encrypted_json(res)


async def init_gacha(request: web.Request) -> web.Response:
    if config.is_wibwob:
        return await init_gacha_wibwob(request)
    return await init_gacha_puni(request)


async def init_goku(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    res = common_response_full()
    res["ywp_mst_goku_story"] = json.loads(
        game_data.gamedata_cache["ywp_mst_goku_story"])["data"]
    res["ywp_mst_goku_menu"] = json.loads(
        game_data.gamedata_cache["ywp_mst_goku_menu"])["data"]
    res["ywp_mst_goku_youkai_intro"] = json.loads(
        game_data.gamedata_cache["ywp_mst_goku_youkai_intro"])["data"]
    res["ywp_mst_goku_youkai_intro_release"] = json.loads(
        game_data.gamedata_cache["ywp_mst_goku_youkai_intro_release"])["data"]

    res["ywp_user_icon_budge"] = await manage_data.get_ywp_user(gdkey, "ywp_user_icon_budge")
    res["ywp_user_goku_story"] = await manage_data.get_ywp_user(gdkey, "ywp_user_goku_story")
    userdata = await YwpUserData.load(gdkey)
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    user_release = await manage_data.get_ywp_user(
        gdkey, "ywp_user_goku_youkai_intro_release") or []

    for item in res["ywp_mst_goku_youkai_intro_release"]:
        found = any(e.get("introReleaseId") == item["introReleaseId"]
                    for e in user_release)
        if not found:
            entry = {
                "updateClearFlg": 0,
                "update": False,
                "updateNowValue": 0,
                "introReleaseId": item["introReleaseId"],
                "userId": userdata.userId if userdata else None,
                "clearFlg": 0 if item.get("clearConditionVal2") else 1,
                "readFlg": 0,
                "missionType": 1,
                "nowValue": 0,
                "createRecord": False,
                "targetValue": item.get("clearConditionVal2", 0),
                "updateReadFlg": 0,
            }
            user_release.append(entry)
    res["ywp_user_goku_youkai_intro_release"] = user_release
    await manage_data.set_ywp_user(gdkey, "ywp_user_goku_youkai_intro_release",
                                   user_release)
    return utils.encrypted_json(res)


def _mst_table(name: str) -> TableParser:
    return TableParser(json.loads(game_data.gamedata_cache[name])["tableData"])


async def init_collect_menu(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    collect_id = req.get("collectId", 0)
    userdata = await YwpUserData.load(gdkey)

    collect_reward_mst = _mst_table("ywp_mst_youkai_collect_reward")
    intro_mst = _mst_table("ywp_mst_youkai_intro")
    collect_mst = _mst_table("ywp_mst_youkai_collect")
    collect_effect_mst = _mst_table("ywp_mst_youkai_collect_effect")

    collect_reward_res = TableParser("")
    intro_res = TableParser("")
    collect_res = TableParser("")
    collect_effect_res = TableParser("")

    user_collect = await manage_data.get_ywp_user(gdkey, "ywp_user_youkai_collect") or []
    user_intro = await manage_data.get_ywp_user(gdkey, "ywp_user_youkai_intro") or []
    res_collect_entries = []
    res_intro_entries = []

    found = False
    for entry in user_collect:
        if entry.get("collectId") == collect_id:
            res_collect_entries.append(entry)
            found = True
    if not found:
        tmp = {"collectId": collect_id, "collectCnt": 0, "menuIdList": ""}
        user_collect.append(tmp)
        res_collect_entries.append(tmp)

    for idx in managers.get_table_indexes(collect_reward_mst, [(0, str(collect_id))]):
        collect_reward_res.add_row(collect_reward_mst.table[idx])
    for idx in managers.get_table_indexes(collect_reward_mst, [(0, str(collect_id))]):
        collect_effect_res.add_row(collect_effect_mst.table[idx])

    for idx in managers.get_table_indexes(collect_mst, [(0, str(collect_id))]):
        found = False
        entry = {}
        for e in user_intro:
            if e.get("introId") == int(collect_mst.table[idx][3]):
                res_intro_entries.append(e)
                found = True
        if not found:
            entry["userId"] = userdata.userId if userdata else None
            entry["introId"] = int(collect_mst.table[idx][3])
        progress = TableParser("")
        collect_res.add_row(collect_mst.table[idx])
        for idx2 in managers.get_table_indexes(intro_mst, [(0, collect_mst.table[idx][3])]):
            intro_res.add_row(intro_mst.table[idx2])
            if not found:
                spe = "1" if not intro_mst.table[idx2][3] else "0"
                progress.add_row([intro_mst.table[idx2][1], spe, "0"])
        if not found:
            entry["progress"] = str(progress)
            res_intro_entries.append(entry)
            user_intro.append(entry)

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict() if userdata else None
    res["truncateItemList"] = None
    res["ywp_mst_youkai_collect_reward"] = str(collect_reward_res)
    res["ywp_mst_youkai_intro"] = str(intro_res)
    res["ywp_mst_youkai_collect"] = str(collect_res)
    res["ywp_mst_youkai_collect_effect"] = str(collect_effect_res)
    res["ywp_user_youkai_collect"] = res_collect_entries
    res["ywp_user_youkai_intro"] = res_intro_entries
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_collect", user_collect)
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_intro", user_intro)
    return utils.encrypted_json(res)


def _crystal_datetime(year, month, day, hour=0, minute=0, second=0) -> dict:
    if year >= 3000:
        unix_time = 253402268399000
        day_of_week = 5
    else:
        dt = datetime(year, month, day, hour, minute, second)
        unix_time = int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        day_of_week = (dt.weekday() + 1) % 7
    return {"date": day, "day": day_of_week, "hours": hour, "minutes": minute,
            "month": month - 1, "seconds": second, "time": unix_time,
            "timezoneOffset": -540, "year": year - 1900}


def _crystal_menu_master() -> list[dict]:
    menu_data = [
        (2927000, 1, "CGet_bushinyan", (2018, 3, 1)),
        (9000294, 2, "CGet_yamabukioni", (2018, 7, 17)),
        (9000263, 3, "CGet_netabarerina", (2018, 6, 16)),
        (9000313, 4, "CGet_hanasakajii", (2018, 9, 17)),
        (9000379, 5, "CGet_ikemenken", (2019, 1, 17)),
        (9000380, 6, "CGet_yamatan", (2019, 1, 17)),
        (9000312, 7, "CGet_shurakoma", (2018, 9, 17)),
        (9000394, 8, "CGet_unchikuma", (2019, 2, 15)),
    ]
    close_dt = _crystal_datetime(8099, 12, 31, 23, 59, 59)
    return [{
        "youkaiId": yid, "openDt": _crystal_datetime(*open_dt),
        "crystalMenuId": mid, "webViewName": name, "closeDt": close_dt,
    } for yid, mid, name, open_dt in menu_data]


async def init_crystal(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    jo = {
        "ywp_mst_crystal_menu": _crystal_menu_master(),
        "shopSaleList": [],
        "ywpToken": "",
        "ymoneyShopSaleList": [],
        "mstVersionMaster": 16774,
        "resultCode": 0,
        "ywp_user_icon_budge": "9000|5*5|1*2000|0*10|1*2007|1*2008|1*2009|1*2010|0*9004|21*9003|0*9007|0*9008|0*9009|0*10959|0*20959|0",
        "nextScreenType": 0,
        "dialogMsg": "",
        "hitodamaShopSaleList": [],
        "webServerIp": "",
        "storeUrl": "",
        "dialogTitle": "",
        "resultType": 0,
        "serverDt": int(time.time() * 1000),
        "ywp_user_data": {
            "birthday": "", "freeHitodama": 3, "friendMaxCnt": 10, "plateId": 1,
            "medalPoint": 0, "webCode": "y1zy12nfflmpxw6q", "nowStageId": 1001006,
            "titleId": 1, "gokuCollectCnt": 0, "ymoney": 3285, "reviewFlg": 0,
            "moveReason": 0, "chargeYmoney": 0, "effectId": 1,
            "crystalCollectCnt": 0, "eventPointUpItemId": 0,
            "characterId": "3qjiw6vi", "iconId": 1,
            "limitTimeSaleRemainSec": 63780, "totMedalPoint": 0,
            "eventPointUpItemRemainSec": 0, "playerName": "superog",
            "todaysRemainSec": 63781, "weeklyFreeFlg": 1, "hitodama": 0,
            "lastRenameDt": 0, "codenameId": 1, "usingItemList": [],
            "hitodamaRecoverSec": 240,
            "limitTimeSaleEndDt": "2025-09-15 23:59:59", "equipWatchId": 10101,
        },
        "ywp_user_crystal_menu": [],
    }
    try:
        device_id = req.get("deviceId")
        if device_id:
            gdkeys = await manage_data.get_gdkeys_from_udkey(device_id)
            if gdkeys:
                tables = await manage_data.get_entire_user_data(gdkeys[0])
                if tables is not None and "ywp_user_data" in tables:
                    jo["ywp_user_data"] = tables["ywp_user_data"]
    except Exception as ex:
        log.warning("crystal menu: could not load user data: %s", ex)
    return utils.encrypted_json(jo)


def _current_week_seq() -> int:
    try:
        now = datetime.utcnow()
        week_of_year = (now.timetuple().tm_yday - 1) // 7 + 1
        return now.year * 100 + min(week_of_year, 53)
    except Exception:
        return 202538


async def _compute_player_total_score(gdkey: str):
    try:
        stage_raw = await manage_data.get_ywp_user(gdkey, "ywp_user_stage")
        if isinstance(stage_raw, list):
            stage_raw = "*".join(stage_raw)
        if not stage_raw:
            return 0, 0
        total_stars = 0
        total_score = 0
        for entry in stage_raw.split('*'):
            if not entry:
                continue
            parts = entry.split('|')
            if len(parts) >= 6:
                for p in parts[2:5]:
                    try:
                        total_stars += int(p)
                    except ValueError:
                        pass
                try:
                    total_score += int(parts[5])
                except ValueError:
                    pass
        return total_stars, total_score
    except Exception as ex:
        log.warning("could not compute total score for %s: %s", gdkey, ex)
        return 0, 0


async def _determine_user_league(gdkey: str) -> int:
    try:
        userdata = await YwpUserData.load(gdkey)
        if userdata is None:
            return 5
        total_stars, total_score = await _compute_player_total_score(gdkey)
        if total_stars >= 1000 or total_score >= 50_000_000:
            return 1
        if total_stars >= 800 or total_score >= 30_000_000:
            return 2
        if total_stars >= 600 or total_score >= 15_000_000:
            return 3
        if total_stars >= 400 or total_score >= 5_000_000:
            return 4
        return 5
    except Exception as ex:
        log.warning("could not determine league for %s: %s", gdkey, ex)
        return 5


async def init_score_attack(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    resdict = common_response_full()
    resdict["responseCode"] = 0
    resdict["weekSeq"] = 0
    resdict["leagueId"] = 0
    tables = ["ywp_user_data", "ywp_user_score_attack_reward",
              "ywp_mst_score_attack_league", "ywp_mst_score_attack_reward",
              "ywp_mst_score_attack_item", "ywp_mst_score_attack",
              "ywp_mst_big_boss"]
    await utils.add_tables_to_response(tables, resdict, False, gdkey or "")
    try:
        resdict["weekSeq"] = _current_week_seq()
        resdict["leagueId"] = await _determine_user_league(gdkey)
        log.debug("score attack init for %s: week %s league %s", gdkey,
                  resdict["weekSeq"], resdict["leagueId"])
    except Exception as ex:
        log.warning("score attack init failed for %s: %s", gdkey, ex)
        resdict["weekSeq"] = 202538
        resdict["leagueId"] = 5
    return utils.encrypted_json(resdict)
