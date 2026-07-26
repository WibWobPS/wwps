from __future__ import annotations

import pytest

from wwps import config, security
from wwps import user_data as manage_data

from .conftest import ADMIN_TOKEN

ADMIN_HEADER = {"X-Admin-Token": ADMIN_TOKEN}


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
    result = await manage_data.admin_adjust("gd-1", ymoney_delta=1000,
                                            hitodama_delta=-1)
    assert result["ymoney"] == 3666
    assert result["hitodama"] == 2
    assert banstore["accounts"]["gd-1"].is_dirty is True


@pytest.mark.asyncio
async def test_admin_adjust_floors_at_zero(banstore):
    result = await manage_data.admin_adjust("gd-1", ymoney_delta=-999999)
    assert result["ymoney"] == 0


@pytest.fixture
async def admin_client(banstore, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    from wwps import app as wwps_app

    async def counts():
        return 1

    monkeypatch.setattr(manage_data, "count_accounts", counts)
    monkeypatch.setattr(manage_data, "count_devices", counts)

    async def record(action, gdkey, detail, actor):
        audit.append((action, gdkey, detail, actor))

    audit: list[tuple] = []
    monkeypatch.setattr(manage_data, "record_admin_action", record)

    application = wwps_app.build_app()
    application.on_startup.clear()
    application.on_cleanup.clear()
    client = TestClient(TestServer(application))
    await client.start_server()
    client.audit = audit
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_admin_handlers_require_a_token(monkeypatch):
    from wwps.handlers import admin

    monkeypatch.setattr(config, "admin_token", None)

    class Req:
        query: dict = {}
        headers: dict = {}
        path = "/admin/stats"
        remote = "127.0.0.1"

    resp = await admin.stats(Req())
    assert resp.status == 503


@pytest.mark.asyncio
async def test_admin_rejects_a_missing_or_wrong_token(admin_client):
    assert (await admin_client.get("/admin/stats")).status == 401
    denied = await admin_client.get("/admin/stats",
                                    headers={"X-Admin-Token": "wrong"})
    assert denied.status == 401


@pytest.mark.asyncio
async def test_admin_does_not_accept_the_token_in_the_url(admin_client):
    response = await admin_client.get(f"/admin/stats?token={ADMIN_TOKEN}")
    assert response.status == 401


@pytest.mark.asyncio
async def test_admin_stats_with_the_header(admin_client):
    response = await admin_client.get("/admin/stats", headers=ADMIN_HEADER)
    assert response.status == 200
    assert (await response.json())["banned"] == 0


@pytest.mark.asyncio
async def test_admin_grant_rejects_a_body_that_is_not_json(admin_client):
    response = await admin_client.post("/admin/grant", data="{",
                                       headers=ADMIN_HEADER)
    assert response.status == 400


@pytest.mark.asyncio
async def test_admin_grant_rejects_an_amount_that_is_not_a_number(admin_client):
    response = await admin_client.post(
        "/admin/grant", json={"gdkey": "gd-1", "ymoney": "lots"},
        headers=ADMIN_HEADER)
    assert response.status == 400


@pytest.mark.asyncio
async def test_admin_grant_rejects_an_amount_out_of_range(admin_client):
    response = await admin_client.post(
        "/admin/grant", json={"gdkey": "gd-1", "ymoney": 10 ** 12},
        headers=ADMIN_HEADER)
    assert response.status == 400


@pytest.mark.asyncio
async def test_admin_actions_are_audited(admin_client, banstore):
    granted = await admin_client.post(
        "/admin/grant", json={"gdkey": "gd-1", "ymoney": 100},
        headers=ADMIN_HEADER)
    assert granted.status == 200
    banned = await admin_client.post(
        "/admin/ban", json={"gdkey": "gd-1", "reason": "cheating"},
        headers=ADMIN_HEADER)
    assert banned.status == 200
    assert banstore["bans"]["gd-1"] == "cheating"
    actions = [entry[0] for entry in admin_client.audit]
    assert actions == ["grant", "ban"]
