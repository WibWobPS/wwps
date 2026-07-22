from __future__ import annotations

import json

from aiohttp import web

from .. import consts, game_data, managers, utils
from .. import user_data as manage_data
from ..dto import TutorialList, common_response_dict, common_response_full
from ..rows import (YwpMstYoukai, YwpMstYoukaiLevel, YwpMstYoukaiLevelOpen,
                    YwpUserDictionary, YwpUserYoukai, YwpUserYoukaiBonusEffect,
                    YwpUserYoukaiDeck, YwpUserYoukaiLegendReleaseHistory,
                    YwpUserYoukaiSkill, parser_for)
from ..ywp_user_data import YwpUserData


async def _str_table(gdkey: str, table: str) -> str | None:
    raw = await manage_data.get_ywp_user(gdkey, table)
    return raw if isinstance(raw, str) else None


def _mst_yokai():
    return parser_for(YwpMstYoukai,
                      game_data.get_table_string_from_json("ywp_mst_youkai"))


async def deck_edit(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserId")
    youkai_id_list = req.get("youkaiIdList") or []

    tutorial_list = TutorialList.parse(
        await manage_data.get_ywp_user(gdkey, "ywp_user_tutorial_list"))
    if tutorial_list.get_status(1000, 1) == 6:
        tutorial_list.edit_tutorial_flg(1, 1000, 7)
    if tutorial_list.get_status(1, 2) == 0:
        tutorial_list.edit_tutorial_flg(2, 1, 1)

    userdata = await YwpUserData.load(gdkey)
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_deck = parser_for(YwpUserYoukaiDeck,
                           await _str_table(gdkey, "ywp_user_youkai_deck"))

    for item in youkai_id_list:
        if managers.get_youkai_index(user_yokai, item["youkaiId"]) == -1:
            return utils.encrypted_json(
                consts.msg_box_response("You dont have this yokai", "Error"))

    deck = user_deck.items[0]
    deck.MiddleYoukaiId = youkai_id_list[0]["youkaiId"]
    deck.MiddleLeftYoukaiId = youkai_id_list[1]["youkaiId"]
    deck.MiddleRightYoukaiId = youkai_id_list[2]["youkaiId"]
    deck.FarLeftYoukaiId = youkai_id_list[3]["youkaiId"]
    deck.FarRightYoukaiId = youkai_id_list[4]["youkaiId"]
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_deck", str(user_deck))

    base = common_response_dict()
    resdict = {
        "serverDt": base["serverDt"],
        "mstVersionMaster": base["mstVersionMaster"],
        "resultCode": 0,
        "resultType": 0,
        "nextScreenType": 0,
        "ymoneyShopSaleList": base["ymoneyShopSaleList"],
        "ywpToken": "",
        "token": "",
        "dialogMsg": "",
    }
    resdict["ywp_user_youkai_deck"] = str(user_deck)
    await manage_data.set_ywp_user(gdkey, "ywp_user_tutorial_list",
                                   tutorial_list.serialize())
    resdict["ywp_user_tutorial_list"] = tutorial_list.serialize()
    userdata.youkaiId = deck.MiddleYoukaiId
    await userdata.save(gdkey)
    resdict["ywp_user_data"] = userdata.to_dict()

    for table in consts.DECK_EDIT_TABLES:
        if table.startswith("ywp_user"):
            table_obj = await manage_data.get_ywp_user(gdkey, table)
        else:
            raw = game_data.gamedata_cache.get(table)
            try:
                table_obj = json.loads(raw)
                if isinstance(table_obj, dict):
                    if "data" in table_obj:
                        table_obj = table_obj["data"]
                    elif "tableData" in table_obj:
                        table_obj = table_obj["tableData"]
            except (json.JSONDecodeError, ValueError, TypeError):
                table_obj = raw
        if table_obj is None:
            table_obj = []
        resdict[table] = table_obj

    response = utils.encrypted_json(resdict)
    await managers.refresh_ywp_user_friend(gdkey, -1, -1, "", userdata.youkaiId, "")
    return response


async def evolve_youkai(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    yokai_id = req.get("youkaiId", 0)

    mst_yokai = _mst_yokai()
    userdata = await YwpUserData.load(gdkey)
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_deck = parser_for(YwpUserYoukaiDeck,
                           await _str_table(gdkey, "ywp_user_youkai_deck"))
    user_dict = parser_for(YwpUserDictionary,
                           await _str_table(gdkey, "ywp_user_dictionary"))

    user_item = next((x for x in user_yokai.items if x.YoukaiId == yokai_id), None)
    if user_item is None:
        return utils.encrypted_json(
            consts.msg_box_response("You don't own this Yo-kai", "Error"))
    mst_item = next((x for x in mst_yokai.items if x.YoukaiId == yokai_id), None)
    if mst_item is None:
        return utils.encrypted_json(
            consts.msg_box_response("Yo-kai doesn't exist", "Error"))
    if user_item.Level < mst_item.EvolutionLevel:
        return utils.encrypted_json(
            consts.msg_box_response("Yo-kai can't evolve yet", "Error"))

    old_level = user_item.Level
    managers.delete_youkai(user_yokai, user_skill, yokai_id, user_bonus)
    managers.edit_dictionary(user_dict, yokai_id, True, False)
    await managers.add_youkai(user_yokai, mst_item.EvolutionYoukaiId, user_skill,
                              user_bonus, gdkey)
    managers.edit_dictionary(user_dict, mst_item.EvolutionYoukaiId, True, True)
    evolved = next(x for x in user_yokai.items
                   if x.YoukaiId == mst_item.EvolutionYoukaiId)
    evolved.Level = old_level

    evo_mst = next(x for x in mst_yokai.items
                   if x.YoukaiId == mst_item.EvolutionYoukaiId)
    level_tbl = parser_for(
        YwpMstYoukaiLevel,
        game_data.get_table_string_from_json("ywp_mst_youkai_level"))
    lvl_idx = managers.mst_youkai_level_index(level_tbl, evo_mst.LevelType, old_level)
    if lvl_idx != -1:
        info = level_tbl.items[lvl_idx]
        evolved.Exp = info.BaseExp
        evolved.ExpDenominator = (info.MaxExp + 1) - info.BaseExp
        evolved.ExpNumerator = 0
        evolved.Percentage = 0
    hp_off = (evo_mst.MaxHp - evo_mst.BaseHp) // evo_mst.MaxLevel
    atk_off = (evo_mst.MaxAtk - evo_mst.BaseAtk) // evo_mst.MaxLevel
    evolved.Hp = evo_mst.BaseHp + hp_off * (old_level - 1)
    evolved.Atk = evo_mst.BaseAtk + atk_off * (old_level - 1)

    deck = user_deck.items[0]
    for slot in ("MiddleYoukaiId", "MiddleLeftYoukaiId", "MiddleRightYoukaiId",
                 "FarRightYoukaiId", "FarLeftYoukaiId"):
        if getattr(deck, slot) == yokai_id:
            setattr(deck, slot, mst_item.EvolutionYoukaiId)

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_dictionary"] = str(user_dict)
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    res["ywp_user_youkai_skill"] = str(user_skill)
    res["ywp_user_youkai_deck"] = str(user_deck)
    res["youkai"] = managers.yokai_won_popup(mst_item.EvolutionYoukaiId, user_yokai,
                                             user_skill)
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                   res["ywp_user_youkai_skill"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   res["ywp_user_youkai_bonus_effect"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_deck",
                                   res["ywp_user_youkai_deck"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary",
                                   res["ywp_user_dictionary"])
    return utils.encrypted_json(res)


async def release_youkai(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    yokai_id = req.get("youkaiId", 0)

    userdata = await YwpUserData.load(gdkey)
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    user_skill = parser_for(YwpUserYoukaiSkill,
                            await _str_table(gdkey, "ywp_user_youkai_skill"))
    user_bonus = parser_for(YwpUserYoukaiBonusEffect,
                            await _str_table(gdkey, "ywp_user_youkai_bonus_effect"))
    user_dict = parser_for(YwpUserDictionary,
                           await _str_table(gdkey, "ywp_user_dictionary"))
    history = parser_for(
        YwpUserYoukaiLegendReleaseHistory,
        await _str_table(gdkey, "ywp_user_youkai_legend_release_history"))

    mst_legend = next((x for x in managers.mst_legend_release_table().items
                       if x.LegendYokaiID == yokai_id), None)
    if mst_legend is None:
        return utils.encrypted_json(
            consts.msg_box_response("Can't find this legend", "Error"))
    if any(x.LegendYokaiID == yokai_id for x in history.items):
        return utils.encrypted_json(
            consts.msg_box_response("You already did this legend", "Error"))

    seals = [mst_legend.Yokai1ID, mst_legend.Yokai2ID, mst_legend.Yokai3ID,
             mst_legend.Yokai4ID, mst_legend.Yokai5ID, mst_legend.Yokai6ID]
    if any(not any(x.YoukaiId == seal for x in user_yokai.items) for seal in seals):
        return utils.encrypted_json(
            consts.msg_box_response("You don't have the required yokai.", "Error"))

    await managers.add_youkai(user_yokai, yokai_id, user_skill, user_bonus, gdkey)
    managers.edit_dictionary(user_dict, yokai_id, True, True)
    history.items.append(YwpUserYoukaiLegendReleaseHistory(LegendYokaiID=yokai_id))

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_dictionary"] = str(user_dict)
    res["ywp_user_youkai_skill"] = str(user_skill)
    res["ywp_user_youkai_bonus_effect"] = str(user_bonus)
    res["ywp_user_youkai_legend_release_history"] = str(history)
    res["youkai"] = managers.yokai_won_popup(yokai_id, user_yokai, user_skill)

    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_skill",
                                   res["ywp_user_youkai_skill"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_bonus_effect",
                                   res["ywp_user_youkai_bonus_effect"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_dictionary",
                                   res["ywp_user_dictionary"])
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai_legend_release_history",
                                   res["ywp_user_youkai_legend_release_history"])
    return utils.encrypted_json(res)


async def level_lock_off(request: web.Request) -> web.Response:
    req = await utils.read_decrypted_request(request)
    gdkey = req.get("level5UserID")
    yokai_id = req.get("youkaiId", 0)

    mst_yokai = parser_for(
        YwpMstYoukai, json.loads(game_data.gamedata_cache["ywp_mst_youkai"])["tableData"])
    user_yokai = parser_for(YwpUserYoukai, await _str_table(gdkey, "ywp_user_youkai"))
    userdata = await YwpUserData.load(gdkey)
    level_open = parser_for(
        YwpMstYoukaiLevelOpen,
        json.loads(game_data.gamedata_cache["ywp_mst_youkai_level_open"])["tableData"])

    rarity = next(x for x in mst_yokai.items if x.YoukaiId == yokai_id).YoukaiRarity
    yokai = next(x for x in user_yokai.items if x.YoukaiId == yokai_id)
    entry = next(x for x in level_open.items
                 if x.RarityType == rarity and x.Level == yokai.Level)
    price = entry.YmoneyCost
    if userdata.ymoney < price:
        return utils.encrypted_json(consts.msg_box_response(
            "You don't have enough Y-Money.", "Too expensive"))
    print(f"[LevelLockOff] Calculated price: {price}")
    userdata.ymoney -= price
    yokai.IsLockedLevel = 0

    res = common_response_full()
    res["ywp_user_data"] = userdata.to_dict()
    res["ywp_user_youkai"] = str(user_yokai)
    res["ywp_user_youkai_skill"] = await _str_table(gdkey, "ywp_user_youkai_skill")
    res["ywp_user_youkai_bonus_effect"] = await _str_table(
        gdkey, "ywp_user_youkai_bonus_effect")
    res["ywp_user_youkai_strong_skill"] = await _str_table(
        gdkey, "ywp_user_youkai_strong_skill")
    res["ywp_user_icon_budge"] = await _str_table(gdkey, "ywp_user_icon_budge")
    await manage_data.set_ywp_user(gdkey, "ywp_user_youkai", res["ywp_user_youkai"])
    await userdata.save(gdkey)
    return utils.encrypted_json(res)
