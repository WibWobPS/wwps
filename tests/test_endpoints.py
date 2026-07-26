from __future__ import annotations

import hashlib
import json
from base64 import b64decode, urlsafe_b64encode
from gzip import decompress

import pytest
from aiohttp.test_utils import TestClient, TestServer
from Cryptodome.Cipher import AES
from Cryptodome.Util.Padding import pad, unpad

from wwps import app as wwps_app
from wwps import metrics, nhn_crypt

SALT = b"0bk2kvtFE2"


def _encrypt(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    digest = hashlib.sha1(SALT + hashlib.sha1(SALT + b" " + raw).digest()).digest()
    return urlsafe_b64encode(AES.new(nhn_crypt.NHN_KEY, AES.MODE_ECB).encrypt(
        pad(digest + raw, 16))).decode()


def _decrypt(token: str) -> dict:
    token = token.replace("-", "+").replace("_", "/")
    token += "=" * ((-len(token)) % 4)
    raw = unpad(AES.new(nhn_crypt.NHN_KEY, AES.MODE_ECB).decrypt(b64decode(token)), 16)
    return json.loads(decompress(raw[20:]).decode())


@pytest.fixture
async def client(store):
    store["devices"]["dev-1"] = ["gd-1"]
    store["tables"]["gd-1"] = {
        "ywp_user_data": {
            "userId": "7", "playerName": "Tester", "iconId": 1, "titleId": 1,
            "ymoney": 1000, "hitodama": 3, "freeHitodama": 2,
            "youkaiId": 2235000, "characterId": "abcd1234", "usingItemList": [],
            "friendMaxCnt": 10, "nowStageId": 1001001},
        "ywp_user_map": "1001|1|0",
        "ywp_user_friend": [], "ywp_user_friend_request_recv": [],
        "ywp_user_friend_star_rank": [], "ywp_user_friend_rank": [],
        "ywp_user_watch": [{"watchId": 10101, "readFlg": 0}],
    }
    application = wwps_app.build_app()
    application.on_startup.clear()
    application.on_cleanup.clear()
    test_client = TestClient(TestServer(application))
    await test_client.start_server()
    yield test_client
    await test_client.close()


async def call(client, path: str, payload: dict):
    response = await client.post(path, data=_encrypt(payload))
    return response.status, _decrypt(await response.text())


@pytest.mark.asyncio
async def test_init_accepts_the_configured_version(client):
    status, body = await call(client, "/init.nhn", {"appVer": "1.0.0"})
    assert status == 200
    assert body["gameServerUrl"].startswith("http")
    assert body["isEnableSerialCode"] == 1


@pytest.mark.asyncio
async def test_init_rejects_another_version(client):
    _, body = await call(client, "/init.nhn", {"appVer": "0.0.1"})
    assert "not\ncompatible" in body["dialogMsg"]
    assert body["resultType"] == 2


@pytest.mark.asyncio
async def test_trailing_slash_reaches_the_same_handler(client):
    status, body = await call(client, "/init.nhn/", {"appVer": "1.0.0"})
    assert status == 200 and "gameServerUrl" in body


@pytest.mark.asyncio
async def test_unknown_path_returns_a_dialog(client):
    _, body = await call(client, "/doesNotExist.nhn", {})
    assert "Unimplemented request" in body["dialogMsg"]


@pytest.mark.asyncio
async def test_buy_hitodama_charges_and_grants(client, store):
    status, body = await call(client, "/buyHitodama.nhn", {
        "level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 1})
    assert status == 200
    assert body["before"]["hitodama"] == 3
    assert body["after"]["hitodama"] == 9
    assert store["tables"]["gd-1"]["ywp_user_data"]["ymoney"] == 900


@pytest.mark.asyncio
async def test_buy_hitodama_refuses_when_broke(client, store):
    store["tables"]["gd-1"]["ywp_user_data"]["ymoney"] = 10
    _, body = await call(client, "/buyHitodama.nhn", {
        "level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 1})
    assert "enough Y Money" in body["dialogMsg"]


@pytest.mark.asyncio
async def test_watch_read_flag_persists(client, store):
    await call(client, "/updateWatchReadFlg.nhn", {
        "level5UserID": "gd-1", "deviceID": "dev-1", "watchId": 10101})
    assert store["tables"]["gd-1"]["ywp_user_watch"][0]["readFlg"] == 1


@pytest.mark.asyncio
async def test_foreign_save_is_rejected(client):
    status, body = await call(client, "/buyHitodama.nhn", {
        "level5UserId": "gd-999", "deviceId": "dev-1", "goodsId": 1})
    assert status == 403
    assert body["dialogTitle"] == "Authentication error"


@pytest.mark.asyncio
async def test_requests_are_counted(client):
    metrics.reset()
    await call(client, "/init.nhn", {"appVer": "1.0.0"})
    snapshot = metrics.snapshot()
    assert snapshot["requests_total"] == 1
    assert snapshot["endpoints"][0]["path"] == "/init.nhn"


@pytest.mark.asyncio
async def test_health_probe_answers(client):
    response = await client.get("/healthz")
    assert response.status == 200
    assert (await response.json())["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_reports_each_check(client):
    response = await client.get("/readyz")
    body = await response.json()
    assert set(body["checks"]) == {"database", "game_data"}
    assert body["checks"]["game_data"] is True
    # No pool is open in the tests, so readiness must be a 503, not a crash.
    assert response.status == 503


@pytest.mark.asyncio
async def test_probes_are_not_counted_in_the_metrics(client):
    metrics.reset()
    await client.get("/healthz")
    assert metrics.snapshot()["requests_total"] == 0


@pytest.mark.asyncio
async def test_unknown_paths_share_one_metric_bucket(client):
    metrics.reset()
    for i in range(50):
        await call(client, f"/nope{i}.nhn", {})
    paths = [row["path"] for row in metrics.snapshot()["endpoints"]]
    assert paths == [metrics.UNMATCHED]


@pytest.mark.asyncio
async def test_a_body_that_is_not_encrypted_is_a_bad_request(client):
    response = await client.post("/init.nhn", data="not an nhn payload")
    assert response.status == 400


@pytest.mark.asyncio
async def test_responses_carry_the_baseline_security_headers(client):
    response = await client.get("/healthz")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.asyncio
async def test_a_forged_host_header_cannot_redirect_clients(client, monkeypatch):
    """The launching payload tells the client where to send everything else.

    Believing X-Forwarded-Host by default lets anyone point players at their
    own server, so it is only honoured when the operator opts in.
    """
    from wwps import config, game_data
    game_data.gamedata_cache["hspLaunchingInfos"] = json.dumps(
        {"imgServer": "http://youtube.com/dd", "lncNotices": []})
    from wwps.handlers import launching
    launching._template = None
    monkeypatch.setattr(config, "public_url", None)
    monkeypatch.setattr(config, "trust_proxy_headers", False)

    response = await client.get("/getLaunchingInfos",
                                headers={"X-Forwarded-Host": "evil.example.com"})
    assert "evil.example.com" not in await response.text()

    monkeypatch.setattr(config, "trust_proxy_headers", True)
    launching._template = None
    response = await client.get("/getLaunchingInfos",
                                headers={"X-Forwarded-Host": "proxy.example.com"})
    assert "proxy.example.com" in await response.text()


@pytest.mark.asyncio
async def test_the_public_url_wins_over_forwarded_headers(client, monkeypatch):
    from wwps import config, game_data
    game_data.gamedata_cache["hspLaunchingInfos"] = json.dumps(
        {"imgServer": "http://youtube.com/dd", "lncNotices": []})
    from wwps.handlers import launching
    launching._template = None
    monkeypatch.setattr(config, "public_url", "https://wwps.example.com")
    monkeypatch.setattr(config, "trust_proxy_headers", True)
    response = await client.get("/getLaunchingInfos",
                                headers={"X-Forwarded-Host": "evil.example.com"})
    body = await response.text()
    assert "wwps.example.com" in body and "evil.example.com" not in body
