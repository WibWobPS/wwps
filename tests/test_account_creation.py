from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wwps import app as wwps_app
from wwps import config
from wwps import user_data as manage_data


@pytest.fixture
async def l5id_client(monkeypatch):
    devices: dict[str, list[str]] = {"dev-1": []}
    created: list[str] = []

    async def is_device_exists(udkey):
        return udkey in devices

    async def new_device(udkey=None):
        udkey = udkey or "generated"
        devices.setdefault(udkey, [])
        return udkey

    async def get_gdkeys_from_udkey(udkey):
        return list(devices.get(udkey, []))

    async def new_account():
        gdkey = f"gd-{len(created) + 1}"
        created.append(gdkey)
        return gdkey

    async def add_account_to_device(udkey, gdkey):
        devices.setdefault(udkey, []).append(gdkey)

    monkeypatch.setattr(manage_data, "is_device_exists", is_device_exists)
    monkeypatch.setattr(manage_data, "new_device", new_device)
    monkeypatch.setattr(manage_data, "get_gdkeys_from_udkey", get_gdkeys_from_udkey)
    monkeypatch.setattr(manage_data, "new_account", new_account)
    monkeypatch.setattr(manage_data, "add_account_to_device", add_account_to_device)

    application = wwps_app.build_app()
    application.on_startup.clear()
    application.on_cleanup.clear()
    client = TestClient(TestServer(application))
    await client.start_server()
    client.devices = devices
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_a_save_is_created_for_a_known_device(l5id_client):
    response = await l5id_client.get("/l5id/api/v1/create_gdkey?udkey=dev-1")
    body = await response.json()
    assert body["result"] is True
    assert l5id_client.devices["dev-1"] == [body["gdkey"]["value"]]


@pytest.mark.asyncio
async def test_an_unknown_device_cannot_create_saves(l5id_client):
    body = await (await l5id_client.get(
        "/l5id/api/v1/create_gdkey?udkey=not-a-device")).json()
    assert body["result"] is False


@pytest.mark.asyncio
async def test_a_malformed_device_id_is_refused(l5id_client):
    body = await (await l5id_client.get(
        "/l5id/api/v1/create_gdkey?udkey=../../etc/passwd")).json()
    assert body["result"] is False


@pytest.mark.asyncio
async def test_the_advertised_save_limit_is_enforced(l5id_client):
    """The client is told max_gdkeys; the server used to enforce nothing.

    Unlimited creation is free database growth and fills the account cache
    until real players are refused.
    """
    for _ in range(config.max_gdkeys_per_device):
        assert (await (await l5id_client.get(
            "/l5id/api/v1/create_gdkey?udkey=dev-1")).json())["result"] is True
    refused = await (await l5id_client.get(
        "/l5id/api/v1/create_gdkey?udkey=dev-1")).json()
    assert refused["result"] is False
    assert len(l5id_client.devices["dev-1"]) == config.max_gdkeys_per_device


@pytest.mark.asyncio
async def test_the_active_endpoint_reports_the_configured_limit(l5id_client):
    body = await (await l5id_client.get("/api/v1/active.nhn?TICKET=dev-1")).json()
    assert body["max_gdkeys"] == config.max_gdkeys_per_device


@pytest.mark.asyncio
async def test_a_malformed_ticket_does_not_create_a_device(l5id_client):
    response = await l5id_client.get("/api/v1/active.nhn?TICKET=%20%20")
    assert response.status == 400
    assert list(l5id_client.devices) == ["dev-1"]
