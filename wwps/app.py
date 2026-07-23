from __future__ import annotations

import asyncio
import functools
import re
import time

from aiohttp import web

from . import (auth, config, consts, dashboard, game_data, logging_setup,
               metrics, security, utils)
from . import user_data as manage_data
from .handlers import (admin, basic, friend, gacha, game, init, l5id,
                       launching, misc, world, yokai)

log = logging_setup.get(__name__)


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
async def metrics_middleware(request: web.Request, handler):
    started = time.perf_counter()
    failed = False
    try:
        response = await handler(request)
        failed = response.status >= 500
        return response
    except Exception:
        failed = True
        raise
    finally:
        if not request.path.startswith("/dashboard"):
            metrics.record_request(request.path,
                                   (time.perf_counter() - started) * 1000, failed)


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except manage_data.ServerFullError:
        metrics.event("warning", "refused a player, account cache is full")
        log.warning("server full, refused %s", request.path)
        return utils.encrypted_json(consts.msg_box_response(
            "The server is full.\nPlease try again later.", "Busy"), status=503)
    except security.BannedError as ex:
        return utils.encrypted_json(consts.msg_box_response(
            str(ex), "Account banned"), status=403)
    except security.OwnershipError as ex:
        return utils.encrypted_json(consts.msg_box_response(
            str(ex), "Authentication error"), status=403)
    except web.HTTPException:
        raise
    except Exception as ex:
        metrics.incr("unhandled_errors")
        metrics.event("critical", f"{request.path}: {type(ex).__name__}: {ex}")
        log.error("unhandled error on %s", request.path, exc_info=True)
        return utils.encrypted_json(consts.msg_box_response(
            "The server hit an internal error.\nPlease try again.",
            config.server_name or "Error"), status=500)


def _post(app: web.Application, path: str, fn):
    app.router.add_post(path, fn)


def build_app() -> web.Application:
    app = web.Application(middlewares=[rewrite_middleware, metrics_middleware,
                                       error_middleware])

    L5ID_BASE = "/api/v1/"
    app.router.add_get("/l5id" + L5ID_BASE + "active", l5id.active_puni)
    app.router.add_get("/l5id" + L5ID_BASE + "create_gdkey", l5id.create_gdkey)
    app.router.add_get(L5ID_BASE + "active.nhn", l5id.active_wibwob)
    app.router.add_get(L5ID_BASE + "create_gdkey.nhn", l5id.create_gdkey)

    async def _auth_link(r):
        return await auth.init_account_action(r, True)

    async def _auth_restore(r):
        return await auth.init_account_action(r, False)

    app.router.add_post("/auth/link", _auth_link)
    app.router.add_post("/auth/restore", _auth_restore)
    app.router.add_get("/help/inquiry/top.nhn", misc.help_inquiry_top)

    app.router.add_route("*", "/hsp", launching.launching)
    app.router.add_route("*", "/hsp/{tail:.*}", launching.launching)
    app.router.add_route("*", "/getLaunchingInfos", launching.launching)

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

    if config.dashboard_enabled:
        app.router.add_get("/dashboard", dashboard.page)
        app.router.add_get("/dashboard/data", dashboard.data)
        app.router.add_get("/dashboard/metrics", dashboard.prometheus)

    app.router.add_get("/admin/stats", admin.stats)
    app.router.add_get("/admin/players", admin.players)
    app.router.add_get("/admin/player/{gdkey}", admin.player)
    app.router.add_post("/admin/grant", admin.grant)
    app.router.add_post("/admin/ban", admin.ban)
    app.router.add_post("/admin/unban", admin.unban)

    app.router.add_route("*", "/{tail:.*}", misc.default_handler)

    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app


async def _on_startup(app: web.Application):
    await manage_data.initialize()
    await manage_data.load_bans()
    metrics.event("good", "server started")
    log.info("loaded %d static game table(s)", len(game_data.gamedata_cache))
    if not config.enforce_account_ownership:
        log.warning("account ownership checks are disabled")
    if config.dashboard_enabled:
        guard = "token required" if config.dashboard_token else "no token set"
        log.info("dashboard on /dashboard (%s)", guard)


async def _on_cleanup(app: web.Application):
    log.info("stopping, flushing accounts")
    try:
        await manage_data.shutdown()
        log.info("flush complete")
    except Exception:
        log.error("flush on shutdown failed", exc_info=True)


def main(argv: list[str] | None = None):
    config.static_init()
    logging_setup.configure(config.log_level)
    game_data.init()
    logging_setup.banner(config.server_name or "WWPS",
                         config.game_version or "unknown",
                         config.port, config.is_wibwob)
    app = build_app()
    web.run_app(app, host="0.0.0.0", port=config.port,
                backlog=config.max_connections, print=None)


if __name__ == "__main__":
    main()
