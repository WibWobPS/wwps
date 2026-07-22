from __future__ import annotations

import asyncio
import functools
import re

from aiohttp import web

from . import auth, config, consts, game_data, utils
from . import user_data as manage_data
from .handlers import basic, friend, gacha, game, init, l5id, misc, world, yokai


def _normalize_path(path: str) -> str:
    path = re.sub(r"^/+", "/", path)
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return path


@web.middleware
async def rewrite_middleware(request: web.Request, handler):
    normalized = _normalize_path(request.path)
    if normalized != request.path:
        request = request.clone(rel_url=normalized + (
            "?" + request.query_string if request.query_string else ""))
    return await handler(request)


@web.middleware
async def server_full_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except manage_data.ServerFullError:
        return utils.encrypted_json(consts.msg_box_response(
            "The server is full.\nPlease try again later.", "Busy"), status=503)


def _post(app: web.Application, path: str, fn):
    app.router.add_post(path, fn)


def build_app() -> web.Application:
    app = web.Application(middlewares=[rewrite_middleware, server_full_middleware])

    L5ID_BASE = "/api/v1/"
    app.router.add_get("/l5id" + L5ID_BASE + "active", l5id.active_puni)
    app.router.add_get("/l5id" + L5ID_BASE + "create_gdkey", l5id.create_gdkey)
    app.router.add_get(L5ID_BASE + "active.nhn", l5id.active_wibwob)
    app.router.add_get(L5ID_BASE + "create_gdkey.nhn", l5id.create_gdkey)

    app.router.add_post("/auth/link",
                        lambda r: auth.init_account_action(r, True))
    app.router.add_post("/auth/restore",
                        lambda r: auth.init_account_action(r, False))
    app.router.add_get("/help/inquiry/top.nhn", misc.help_inquiry_top)

    _post(app, "/init.nhn", init.init)
    _post(app, "/initBilling.nhn", init.init_billing)
    _post(app, "/initGacha.nhn", init.init_gacha)
    _post(app, "/initGoku.nhn", init.init_goku)
    _post(app, "/initCollectMenu.nhn", init.init_collect_menu)
    _post(app, "/initCrystal.nhn", init.init_crystal)
    _post(app, "/initScoreAttack.nhn", init.init_score_attack)

    _post(app, "/getMaster.nhn", basic.get_master)
    _post(app, "/createUser.nhn", basic.create_user)
    _post(app, "/login.nhn", basic.login)
    _post(app, "/conflate.nhn", basic.conflate)
    _post(app, "/getGdkeyAccounts.nhn", basic.get_gdkey_accounts)
    _post(app, "/updateTutorialFlg.nhn", basic.update_tutorial_flag)
    _post(app, "/getL5idStatus.nhn", basic.get_l5id_status)
    _post(app, "/updateProfile.nhn", basic.update_profile)
    _post(app, "/deleteUser.nhn", basic.delete_user)
    _post(app, "/userInfoRefresh.nhn", basic.user_info_refresh)
    _post(app, "/rename.nhn", basic.rename)

    _post(app, "/evolveYoukai.nhn", yokai.evolve_youkai)
    _post(app, "/releaseYoukai.nhn", yokai.release_youkai)
    _post(app, "/deckEdit.nhn", yokai.deck_edit)
    _post(app, "/levelLockOff.nhn", yokai.level_lock_off)

    _post(app, "/initWatch.nhn", misc.init_watch)
    _post(app, "/updateWatchReadFlg.nhn", misc.update_watch_read_flg)
    _post(app, "/serialConfirm.nhn", misc.serial_confirm)
    _post(app, "/ageConfirm.nhn", misc.age_confirm)
    _post(app, "/getLimitHitodama.nhn", misc.get_limit_hitodama)
    _post(app, "/useAddition.nhn", misc.use_addition)
    _post(app, "/updateGokuStory.nhn", misc.update_goku_story)
    _post(app, "/updateGokuMenu.nhn", misc.update_goku_menu)
    _post(app, "/updateCrystalMenu.nhn", misc.update_crystal_menu)
    _post(app, "/updateCollectMenu.nhn", misc.update_collect_menu)
    _post(app, "/getPresentBox.nhn", misc.get_present_box)
    _post(app, "/getRanking.nhn", misc.get_ranking)
    _post(app, "/userStageRanking.nhn", misc.user_stage_ranking)

    _post(app, "/missionReward.nhn", world.mission_reward)
    _post(app, "/getMission.nhn", functools.partial(world.get_mission,
                                                    already_reward_is_appear=0))
    _post(app, "/buyHitodama.nhn", world.buy_hitodama)
    _post(app, "/buyItem.nhn", world.buy_item)
    _post(app, "/useItem.nhn", world.use_item)
    _post(app, "/map.nhn", world.map_)
    _post(app, "/mapWarp.nhn", world.map_warp)
    _post(app, "/mapUnLock.nhn", world.map_unlock)
    _post(app, "/loginStamp.nhn", world.login_stamp)

    _post(app, "/gameStart.nhn", game.game_start)
    _post(app, "/gameEnd.nhn", game.game_end)
    _post(app, "/gameRetire.nhn", game.game_retire)
    _post(app, "/gameUseItem.nhn", game.game_use_item)
    _post(app, "/gameContinue.nhn", game.game_continue)
    _post(app, "/gameStartScoreAttack.nhn", game.game_start_score_attack)
    _post(app, "/gameEndScoreAttack.nhn", game.game_end_score_attack)

    _post(app, "/executeGacha.nhn", gacha.execute_gacha)
    _post(app, "/gacha.nhn", gacha.execute_gacha)

    _post(app, "/friend.nhn", friend.friend)
    _post(app, "/friendSearch.nhn", friend.friend_search)
    _post(app, "/friendRequest.nhn", friend.friend_request)
    _post(app, "/friendRequestDelete.nhn", friend.friend_request_delete)
    _post(app, "/friendRequestAccept.nhn", friend.friend_request_accept)
    _post(app, "/friendDelete.nhn", friend.friend_delete)

    app.router.add_route("*", "/{tail:.*}", misc.default_handler)

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


async def _on_startup(app: web.Application):
    await manage_data.initialize()


async def _on_cleanup(app: web.Application):
    print("server stopping: flushing accounts")
    try:
        await manage_data.shutdown()
        print("flush complete")
    except Exception as ex:
        print(ex)


def main(argv: list[str] | None = None):
    config.static_init()
    game_data.init()
    app = build_app()
    web.run_app(app, host="0.0.0.0", port=8080,
                backlog=config.max_connections)


if __name__ == "__main__":
    main()
