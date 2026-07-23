from __future__ import annotations

import pytest

from wwps import config, security
from wwps import user_data as manage_data


@pytest.fixture
def banstore(monkeypatch):
    bans: dict[str, str] = {}
    accounts: dict[str, dict] = {}

    monkeypatch.setattr(manage_data, "_bans", bans, raising=False)
    monkeypatch.setattr(manage_data, "is_banned", lambda g: g in bans)
    monkeypatch.setattr(manage_data, "ban_reason", lambda g: bans.get(g))

    async def add_ban(gdkey, reason):
        bans[gdkey] = reason

    async def remove_ban(gdkey):
        return bans.pop(gdkey, None) is not None

    monkeypatch.setattr(manage_data, "add_ban", add_ban)
    monkeypatch.setattr(manage_data, "remove_ban", remove_ban)

    class Acc:
        def __init__(self, gdkey, tables):
            self.gdkey = gdkey
            self.character_id = "abcd1234"
            self.user_id = "7"
            self.udkey = "dev-1"
            self.last_login_time = "2026-01-01 00:00:00"
            self.ywp_user_tables = tables
            self.is_dirty = False

    accounts["gd-1"] = Acc("gd-1", {"ywp_user_data": {
        "playerName": "Math", "ymoney": 2666, "hitodama": 3, "freeHitodama": 2,
        "nowStageId": 1001001}, "ywp_user_youkai": "1|1*2|1", "ywp_user_item": "10|3",
        "ywp_user_friend": []})

    async def get_account_from_gdkey(gdkey):
        return accounts.get(gdkey)

    monkeypatch.setattr(manage_data, "get_account_from_gdkey", get_account_from_gdkey)

    async def get_device_gdkeys(udkey):
        return ["gd-1"] if udkey == "dev-1" else None

    monkeypatch.setattr(manage_data, "get_device_gdkeys", get_device_gdkeys)
    return {"bans": bans, "accounts": accounts}


@pytest.mark.asyncio
async def test_banned_account_is_blocked(banstore):
    banstore["bans"]["gd-1"] = "cheating"
    with pytest.raises(security.BannedError) as exc:
        await security.enforce_ownership(
            {"level5UserId": "gd-1", "deviceId": "dev-1"}, "/login.nhn")
    assert "cheating" in str(exc.value)


@pytest.mark.asyncio
async def test_unbanned_account_passes(banstore):
    await security.enforce_ownership(
        {"level5UserId": "gd-1", "deviceId": "dev-1"}, "/login.nhn")


@pytest.mark.asyncio
async def test_ban_takes_precedence_over_ownership(banstore):
    banstore["bans"]["gd-1"] = "x"
    with pytest.raises(security.BannedError):
        await security.enforce_ownership(
            {"level5UserId": "gd-1", "deviceId": "wrong-device"}, "/login.nhn")


@pytest.mark.asyncio
async def test_admin_summary_counts_collections(banstore):
    summary = await manage_data.admin_player_summary("gd-1")
    assert summary["playerName"] == "Math"
    assert summary["ymoney"] == 2666
    assert summary["youkaiCount"] == 2
    assert summary["itemCount"] == 1
    assert summary["banned"] is False


@pytest.mark.asyncio
async def test_admin_summary_missing_player(banstore):
    assert await manage_data.admin_player_summary("nope") is None


@pytest.mark.asyncio
async def test_admin_adjust_changes_currency(banstore):
    manage_data._account_locks  # ensure attribute exists
    result = await manage_data.admin_adjust("gd-1", ymoney_delta=1000,
                                            hitodama_delta=-1)
    assert result["ymoney"] == 3666
    assert result["hitodama"] == 2
    assert banstore["accounts"]["gd-1"].is_dirty is True


@pytest.mark.asyncio
async def test_admin_adjust_floors_at_zero(banstore):
    result = await manage_data.admin_adjust("gd-1", ymoney_delta=-999999)
    assert result["ymoney"] == 0


@pytest.mark.asyncio
async def test_admin_handlers_require_a_token(monkeypatch):
    from wwps.handlers import admin

    monkeypatch.setattr(config, "admin_token", None)

    class Req:
        query = {}
        headers = {}

    resp = await admin.stats(Req())
    assert resp.status == 503


@pytest.mark.asyncio
async def test_admin_handlers_reject_a_wrong_token(monkeypatch):
    from wwps.handlers import admin

    monkeypatch.setattr(config, "admin_token", "secret")

    class Req:
        query = {"token": "wrong"}
        headers = {}

    resp = await admin.stats(Req())
    assert resp.status == 401
