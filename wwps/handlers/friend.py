from __future__ import annotations

from datetime import datetime

from aiohttp import web

from .. import consts, managers, utils
from .. import user_data as manage_data
from ..dto import common_response_full
from ..ywp_user_data import YwpUserData


async def _list(gdkey: str, table: str) -> list:
    return await manage_data.get_ywp_user(gdkey, table) or []


async def friend(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    res = common_response_full()
    res["ywp_user_data"] = None
    recv = await _list(gdkey, "ywp_user_friend_request_recv")
    for item in recv:
        item["requestDtSentence"] = managers.get_time_difference_string(
            item.get("requestDt"))
    res["ywp_user_friend_request_recv"] = recv
    friends = await _list(gdkey, "ywp_user_friend")
    for item in friends:
        item["lastPlayDtSentence"] = managers.get_time_difference_string(
            item.get("lastPlayDt"))
    res["ywp_user_friend"] = friends
    res["ywp_user_friend_star_rank"] = await _list(gdkey, "ywp_user_friend_star_rank")
    res["ywp_user_friend_rank"] = await _list(gdkey, "ywp_user_friend_rank")
    return utils.encrypted_json(res)


async def friend_search(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    target_gdkey = await manage_data.get_gdkey_from_character_id(
        req.get("targetCharacterId") or "")
    res = common_response_full()
    res["friend"] = None
    res["responseCode"] = 1
    if target_gdkey:
        target = await YwpUserData.load(target_gdkey)
        if target is not None:
            res["responseCode"] = 0
            res["friend"] = {
                "iconId": target.iconId,
                "playerName": target.playerName,
                "youkaiId": target.youkaiId,
                "lastPlayDtSentence": "🥺​",
                "titleId": target.titleId,
                "characterId": target.characterId,
                "lastPlayDt": await manage_data.get_last_login_time(target_gdkey),
                "userId": target.userId,
            }
    return utils.encrypted_json(res)


async def friend_request(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    target_user_id = req.get("targetUserId")
    target_gdkey = await manage_data.get_gdkey_from_user_id(target_user_id or "")

    res = common_response_full()
    res["responseCode"] = 0
    res["ywp_user_friend_request_recv"] = None
    good = False
    if target_gdkey:
        my = await YwpUserData.load(gdkey)
        target = await YwpUserData.load(target_gdkey)
        good = target is not None and my is not None
        if good:
            good = target_user_id != my.userId
        if good:
            my_friends = await _list(gdkey, "ywp_user_friend")
            target_friends = await _list(target_gdkey, "ywp_user_friend")
            if len(target_friends) > target.friendMaxCnt:
                res["responseCode"] = 2
            elif len(my_friends) > my.friendMaxCnt:
                res["responseCode"] = 1
            else:
                target_reqs = await _list(target_gdkey, "ywp_user_friend_request_recv")
                for i, element in enumerate(target_reqs):
                    if element.get("userId") == my.userId:
                        target_reqs.pop(i)
                        break
                while len(target_friends) >= 50:
                    target_friends.pop(0)
                target_reqs.append({
                    "playerName": my.playerName,
                    "requestDt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "iconId": my.iconId,
                    "youkaiId": my.youkaiId,
                    "requestDtSentence": "​",
                    "titleId": my.titleId,
                    "characterId": my.characterId,
                    "userId": my.userId,
                })
                await manage_data.set_ywp_user(
                    target_gdkey, "ywp_user_friend_request_recv", target_reqs)
    if not good:
        return utils.encrypted_json(
            consts.msg_box_response("Error occured", "Error"))
    recv = await _list(gdkey, "ywp_user_friend_request_recv")
    for item in recv:
        item["requestDtSentence"] = managers.get_time_difference_string(
            item.get("requestDt"))
    res["ywp_user_friend_request_recv"] = recv
    return utils.encrypted_json(res)


async def friend_request_delete(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    target_user_id = req.get("targetUserId")
    res = common_response_full()
    res["responseCode"] = 0
    recv = await _list(gdkey, "ywp_user_friend_request_recv")
    to_delete = -1
    for i, element in enumerate(recv):
        if element.get("userId") == target_user_id:
            if to_delete == -1:
                to_delete = i
        else:
            element["requestDtSentence"] = managers.get_time_difference_string(
                element.get("requestDt"))
    if to_delete != -1:
        recv.pop(to_delete)
    res["ywp_user_friend_request_recv"] = recv
    await manage_data.set_ywp_user(gdkey, "ywp_user_friend_request_recv", recv)
    return utils.encrypted_json(res)


def _create_user_rank(target_user_id: str, send: list, recv: list):
    for element in send:
        if element.get("self") == 1:
            if not any(e and e.get("userId") == target_user_id for e in recv):
                recv.append({
                    "iconId": element.get("iconId"),
                    "playerName": element.get("playerName"),
                    "titleId": element.get("titleId"),
                    "getStar": element.get("getStar"),
                    "userId": element.get("userId"),
                    "dicCnt": element.get("dicCnt"),
                    "score": element.get("score"),
                    "youkaiId": element.get("youkaiId"),
                    "getStarModiDt": element.get("getStarModiDt"),
                    "hitodamaSendFlg": 0,
                    "onedariSendFlg": 0,
                    "rank": 1,
                    "self": 0,
                })
            break


async def friend_request_accept(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    target_user_id = req.get("targetUserId")

    res = common_response_full()
    my = await YwpUserData.load(gdkey)
    tgdkey = await manage_data.get_gdkey_from_user_id(target_user_id or "")
    target_reqs = await _list(tgdkey, "ywp_user_friend_request_recv")
    my_reqs = await _list(gdkey, "ywp_user_friend_request_recv")
    res["ywp_user_friend_request_recv"] = my_reqs
    res["ywp_user_friend"] = None
    res["responseCode"] = 1
    target_friends = None
    usr = None

    for i, element in enumerate(my_reqs):
        if element.get("userId") == target_user_id:
            target_data = await YwpUserData.load(tgdkey)
            my_reqs.pop(i)
            last_play = await manage_data.get_last_login_time(tgdkey)
            usr = {
                "youkaiId": target_data.youkaiId,
                "userId": target_data.userId,
                "characterId": target_data.characterId,
                "onedariSendFlg": 0,
                "hitodamaSendFlg": 0,
                "mapLockSendFlg": 0,
                "playerName": target_data.playerName,
                "iconId": target_data.iconId,
                "lastPlayDt": last_play,
                "lastPlayDtSentence": managers.get_time_difference_string(last_play),
                "titleId": target_data.titleId,
            }
            break

    if usr is not None:
        my_last_play = await manage_data.get_last_login_time(gdkey)
        me = {
            "youkaiId": my.youkaiId,
            "userId": my.userId,
            "characterId": my.characterId,
            "onedariSendFlg": 0,
            "hitodamaSendFlg": 0,
            "mapLockSendFlg": 0,
            "playerName": my.playerName,
            "iconId": my.iconId,
            "lastPlayDt": my_last_play,
            "lastPlayDtSentence": managers.get_time_difference_string(
                usr["lastPlayDt"]),
            "titleId": my.titleId,
        }
        res["ywp_user_friend"] = await _list(gdkey, "ywp_user_friend")
        res["responseCode"] = 0
        target_friends = await _list(tgdkey, "ywp_user_friend")
        if not any(x.get("userId") == usr["userId"] for x in res["ywp_user_friend"]):
            res["ywp_user_friend"].append(usr)
        if not any(x.get("userId") == me["userId"] for x in target_friends):
            target_friends.append(me)

    for i, element in enumerate(target_reqs):
        if element.get("userId") == my.userId:
            target_reqs.pop(i)
            break

    my_star = await _list(gdkey, "ywp_user_friend_star_rank")
    other_star = await _list(tgdkey, "ywp_user_friend_star_rank")
    my_rank = await _list(gdkey, "ywp_user_friend_rank")
    other_rank = await _list(tgdkey, "ywp_user_friend_rank")
    my_dict_rank = await _list(gdkey, "ywp_user_friend_dictionary_rank")
    other_dict_rank = await _list(tgdkey, "ywp_user_friend_dictionary_rank")

    _create_user_rank(target_user_id, other_star, my_star)
    _create_user_rank(gdkey, my_star, other_star)
    _create_user_rank(target_user_id, other_rank, my_rank)
    _create_user_rank(gdkey, my_rank, other_rank)
    _create_user_rank(target_user_id, other_dict_rank, my_dict_rank)
    _create_user_rank(gdkey, my_dict_rank, other_dict_rank)

    res["ywp_user_friend_star_rank"] = my_star
    res["ywp_user_friend_rank"] = my_rank

    await manage_data.set_ywp_user(gdkey, "ywp_user_friend_star_rank", my_star)
    await manage_data.set_ywp_user(tgdkey, "ywp_user_friend_star_rank", other_star)
    await manage_data.set_ywp_user(gdkey, "ywp_user_friend_rank", my_rank)
    await manage_data.set_ywp_user(tgdkey, "ywp_user_friend_rank", other_rank)
    await manage_data.set_ywp_user(gdkey, "ywp_user_friend_dictionary_rank",
                                   my_dict_rank)
    await manage_data.set_ywp_user(tgdkey, "ywp_user_friend_dictionary_rank",
                                   other_dict_rank)
    await manage_data.set_ywp_user(gdkey, "ywp_user_friend_request_recv", my_reqs)
    if res["ywp_user_friend"] is not None:
        await manage_data.set_ywp_user(gdkey, "ywp_user_friend", res["ywp_user_friend"])
    if target_friends is not None:
        await manage_data.set_ywp_user(tgdkey, "ywp_user_friend", target_friends)
    await manage_data.set_ywp_user(tgdkey, "ywp_user_friend_request_recv", target_reqs)
    return utils.encrypted_json(res)


async def _remove_friend_from_all_tables(gdkey: str, removed_user_id: str):
    for table in ("ywp_user_friend", "ywp_user_friend_rank",
                  "ywp_user_friend_star_rank", "ywp_user_friend_request_recv"):
        entries = await _list(gdkey, table)
        entries = [f for f in entries if f and f.get("userId") != removed_user_id]
        await manage_data.set_ywp_user(gdkey, table, entries)


async def friend_delete(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    target_user_id = req.get("targetUserId")
    res = common_response_full()
    res["responseCode"] = 1

    if not gdkey or not target_user_id:
        return utils.encrypted_json(res)
    my = await YwpUserData.load(gdkey)
    if my is None or not my.userId:
        return utils.encrypted_json(res)

    try:
        target_gdkey = await manage_data.get_gdkey_from_user_id(target_user_id)
    except Exception:
        target_gdkey = None

    my_friends = await _list(gdkey, "ywp_user_friend")
    my_friends = [f for f in my_friends if f and f.get("userId") != target_user_id]
    await manage_data.set_ywp_user(gdkey, "ywp_user_friend", my_friends)
    await _remove_friend_from_all_tables(gdkey, target_user_id)

    if target_gdkey:
        target_friends = await _list(target_gdkey, "ywp_user_friend")
        target_friends = [f for f in target_friends
                          if f and f.get("userId") != my.userId]
        await manage_data.set_ywp_user(target_gdkey, "ywp_user_friend", target_friends)
        await _remove_friend_from_all_tables(target_gdkey, my.userId)

    res["ywp_user_data"] = my.to_dict()
    res["ywp_user_friend"] = await _list(gdkey, "ywp_user_friend")
    res["ywp_user_friend_rank"] = await _list(gdkey, "ywp_user_friend_rank")
    res["ywp_user_friend_star_rank"] = await _list(gdkey, "ywp_user_friend_star_rank")
    res["ywp_user_friend_request_recv"] = await _list(
        gdkey, "ywp_user_friend_request_recv")
    res["responseCode"] = 0
    return utils.encrypted_json(res)
