from __future__ import annotations

import time

from . import config, logging_setup, metrics
from . import user_data as manage_data

log = logging_setup.get(__name__)

GDKEY_FIELDS = ("level5UserId", "level5UserID", "gdkeyValue", "gdkey")
UDKEY_FIELDS = ("deviceId", "deviceID", "udkey")

CLOCK_SKEW_MS = 5000
SCORE_GRACE = 1_000_000

_ownership_cache: set[tuple[str, str]] = set()


class OwnershipError(Exception):
    pass


def clear_ownership_cache():
    _ownership_cache.clear()


def extract_keys(payload: dict) -> tuple[str | None, str | None]:
    gdkey = None
    udkey = None
    for field in GDKEY_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value and value != "0":
            gdkey = value
            break
    for field in UDKEY_FIELDS:
        value = payload.get(field)
        if isinstance(value, str) and value and value != "0":
            udkey = value
            break
    return gdkey, udkey


async def is_owner(udkey: str, gdkey: str) -> bool:
    if (udkey, gdkey) in _ownership_cache:
        return True
    gdkeys = await manage_data.get_device_gdkeys(udkey)
    if gdkeys and gdkey in gdkeys:
        _ownership_cache.add((udkey, gdkey))
        return True
    account = await manage_data.get_account_from_gdkey(gdkey)
    if account is not None and account.udkey and account.udkey == udkey:
        _ownership_cache.add((udkey, gdkey))
        return True
    return False


async def enforce_ownership(payload: dict, path: str):
    if not config.enforce_account_ownership:
        return
    gdkey, udkey = extract_keys(payload)
    if gdkey is None:
        return
    if udkey is None:
        metrics.incr("auth_missing_device")
        log.warning("no device id sent for gdkey %s on %s", gdkey[:8], path)
        raise OwnershipError("Missing device id")
    if not await is_owner(udkey, gdkey):
        metrics.incr("auth_rejected")
        metrics.event("critical",
                      f"ownership rejected on {path} (device {udkey[:8]})")
        log.warning("ownership rejected: device %s does not own gdkey %s on %s",
                    udkey[:8], gdkey[:8], path)
        raise OwnershipError("This save does not belong to this device")


def battle_elapsed_ms(request_id: str) -> int | None:
    try:
        started = int(request_id)
    except (TypeError, ValueError):
        return None
    return int(time.time() * 1000) - started


def validate_battle(payload: dict, request_id: str) -> str | None:
    elapsed = battle_elapsed_ms(request_id)
    if elapsed is None:
        return None

    clear_time = payload.get("clearTimeSec") or 0
    if clear_time * 1000 > elapsed + CLOCK_SKEW_MS:
        metrics.incr("cheat_clear_time")
        return (f"reported clear time {clear_time}s exceeds elapsed "
                f"{elapsed / 1000:.1f}s")

    score = payload.get("score") or 0
    cap = SCORE_GRACE + int(elapsed / 1000.0) * config.max_score_per_second
    if score > cap:
        metrics.incr("cheat_score_cap")
        return f"score {score} above cap {cap}"

    return None


def _deck_slots(deck) -> list[int]:
    return [deck.MiddleYoukaiId, deck.MiddleLeftYoukaiId, deck.MiddleRightYoukaiId,
            deck.FarLeftYoukaiId, deck.FarRightYoukaiId]


def build_lot_pattern(payload: dict, deck) -> str:
    uses = {}
    for entry in payload.get("userYoukaiResultList") or []:
        uses[entry.get("youkaiId")] = entry.get("skillUseNum", 0)
    digits = []
    for youkai_id in _deck_slots(deck):
        count = uses.get(youkai_id, 0)
        digits.append(str(min(max(int(count), 0), 3)))
    return "".join(digits)


def food_bit(enemy_result: dict) -> int:
    if enemy_result.get("useItemLLarge"):
        return 4
    if enemy_result.get("useItemLarge"):
        return 3
    if enemy_result.get("UseItemMiddle") or enemy_result.get("useItemMiddle"):
        return 2
    if enemy_result.get("useItemSmall"):
        return 1
    return 0


def befriend_allowed(enemy_result: dict, stored_enemy: dict | None,
                     pattern: str) -> bool:
    if not config.validate_befriend:
        return True
    if stored_enemy is None:
        return False

    from .dto import LotYoukaiInfoList
    try:
        entries = LotYoukaiInfoList.parse(
            stored_enemy.get("lotYoukaiInfoList")).entries
    except (ValueError, TypeError):
        return False
    if not entries:
        return False

    match = next((e for e in entries if e.get("lotPattern") == pattern), None)
    if match is None:
        match = entries[0]
    result = match.get("lotResult") or ""
    bit = food_bit(enemy_result)
    if bit >= len(result):
        return False
    return result[bit] == "1"
