from __future__ import annotations

import time

import pytest

from wwps import config, security


def test_extract_keys_handles_both_spellings():
    assert security.extract_keys({"level5UserId": "g", "deviceId": "d"}) == ("g", "d")
    assert security.extract_keys({"level5UserID": "g", "deviceID": "d"}) == ("g", "d")
    assert security.extract_keys({"gdkeyValue": "g", "udkey": "d"}) == ("g", "d")


def test_extract_keys_ignores_placeholder_zero():
    assert security.extract_keys({"level5UserID": "0", "deviceID": "d"}) == (None, "d")


@pytest.mark.asyncio
async def test_ownership_accepts_a_device_that_owns_the_save(store):
    store["devices"]["dev-1"] = ["gd-1"]
    await security.enforce_ownership({"level5UserId": "gd-1", "deviceId": "dev-1"},
                                     "/login.nhn")


@pytest.mark.asyncio
async def test_ownership_rejects_a_foreign_save(store):
    store["devices"]["dev-1"] = ["gd-1"]
    with pytest.raises(security.OwnershipError):
        await security.enforce_ownership(
            {"level5UserId": "gd-2", "deviceId": "dev-1"}, "/login.nhn")


@pytest.mark.asyncio
async def test_ownership_rejects_a_missing_device(store):
    with pytest.raises(security.OwnershipError):
        await security.enforce_ownership({"level5UserId": "gd-1"}, "/login.nhn")


@pytest.mark.asyncio
async def test_ownership_skips_payloads_without_a_gdkey(store):
    await security.enforce_ownership({"deviceID": "dev-1"}, "/getGdkeyAccounts.nhn")


@pytest.mark.asyncio
async def test_ownership_can_be_disabled(store, monkeypatch):
    monkeypatch.setattr(config, "enforce_account_ownership", False)
    await security.enforce_ownership({"level5UserId": "gd-9", "deviceId": "dev-1"},
                                     "/login.nhn")


def _request_id(seconds_ago: float) -> str:
    return str(int((time.time() - seconds_ago) * 1000))


def test_battle_accepts_a_plausible_result():
    assert security.validate_battle(
        {"clearTimeSec": 40, "score": 120_000}, _request_id(90)) is None


def test_battle_rejects_impossible_clear_time():
    rejection = security.validate_battle(
        {"clearTimeSec": 300, "score": 1000}, _request_id(20))
    assert rejection is not None and "clear time" in rejection


def test_battle_rejects_an_absurd_score():
    rejection = security.validate_battle(
        {"clearTimeSec": 10, "score": 10_000_000_000}, _request_id(30))
    assert rejection is not None and "score" in rejection


def test_battle_ignores_a_malformed_request_id():
    assert security.validate_battle({"clearTimeSec": 1, "score": 1}, "abc") is None


class _Deck:
    def __init__(self, ids):
        (self.MiddleYoukaiId, self.MiddleLeftYoukaiId, self.MiddleRightYoukaiId,
         self.FarLeftYoukaiId, self.FarRightYoukaiId) = ids


def test_lot_pattern_maps_deck_slots_to_soultimate_uses():
    deck = _Deck([1, 2, 3, 4, 5])
    payload = {"userYoukaiResultList": [
        {"youkaiId": 1, "skillUseNum": 2},
        {"youkaiId": 4, "skillUseNum": 9},
    ]}
    assert security.build_lot_pattern(payload, deck) == "20030"


def test_food_bit_picks_the_highest_tier():
    assert security.food_bit({}) == 0
    assert security.food_bit({"useItemSmall": 1}) == 1
    assert security.food_bit({"UseItemMiddle": 1}) == 2
    assert security.food_bit({"useItemLarge": 1}) == 3
    assert security.food_bit({"useItemLLarge": 1, "useItemSmall": 1}) == 4


def _stored(pattern="00000", result="10000"):
    return {"enemyId": 1, "lotYoukaiInfoList": [
        {"lotPattern": pattern, "lotResult": result}]}


def test_befriend_allowed_when_the_bit_is_set():
    assert security.befriend_allowed({}, _stored(result="10000"), "00000") is True


def test_befriend_rejected_when_the_bit_is_clear():
    assert security.befriend_allowed({}, _stored(result="01111"), "00000") is False


def test_befriend_rejected_without_a_stored_enemy():
    assert security.befriend_allowed({}, None, "00000") is False


def test_befriend_uses_the_food_tier_bit():
    stored = _stored(result="00010")
    assert security.befriend_allowed({"useItemLarge": 1}, stored, "00000") is True
    assert security.befriend_allowed({"useItemSmall": 1}, stored, "00000") is False


def test_befriend_check_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "validate_befriend", False)
    assert security.befriend_allowed({}, None, "00000") is True
