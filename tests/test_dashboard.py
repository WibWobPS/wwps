from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from wwps import app as wwps_app
from wwps import config, metrics

from .conftest import DASHBOARD_TOKEN

HEADER = {"X-Dashboard-Token": DASHBOARD_TOKEN}


@pytest.fixture
async def client(store):
    application = wwps_app.build_app()
    application.on_startup.clear()
    application.on_cleanup.clear()
    test_client = TestClient(TestServer(application))
    await test_client.start_server()
    yield test_client
    await test_client.close()


@pytest.mark.asyncio
async def test_page_is_served(client):
    page = await client.get("/dashboard")
    assert page.status == 200
    assert "WWPS status" in await page.text()
    assert "Content-Security-Policy" in page.headers


@pytest.mark.asyncio
async def test_data_requires_the_token(client):
    assert (await client.get("/dashboard/data")).status == 401
    assert (await client.get("/dashboard/data",
                             headers={"X-Dashboard-Token": "wrong"})).status == 401
    response = await client.get("/dashboard/data", headers=HEADER)
    assert response.status == 200
    payload = await response.json()
    assert payload["server"] == "WWPS test"
    assert len(payload["series"]) == 60


@pytest.mark.asyncio
async def test_the_token_is_not_accepted_in_the_query_string(client):
    # A token in the URL ends up in access logs and Referer headers.
    response = await client.get(f"/dashboard/data?token={DASHBOARD_TOKEN}")
    assert response.status == 401


@pytest.mark.asyncio
async def test_prometheus_requires_the_token(client):
    assert (await client.get("/dashboard/metrics")).status == 401
    body = await (await client.get("/dashboard/metrics", headers=HEADER)).text()
    assert "wwps_requests_total" in body
    assert "wwps_uptime_seconds" in body


@pytest.mark.asyncio
async def test_prometheus_labels_cannot_break_out(client):
    metrics.reset()
    metrics.record_request('/evil" injected="yes\nwwps_fake 1', 1.0, False)
    body = await (await client.get("/dashboard/metrics", headers=HEADER)).text()
    assert "\nwwps_fake 1" not in body
    assert '\\"' in body


@pytest.mark.asyncio
async def test_no_route_is_registered_without_a_token(store, monkeypatch):
    monkeypatch.setattr(config, "dashboard_token", None)
    application = wwps_app.build_app()
    application.on_startup.clear()
    application.on_cleanup.clear()
    test_client = TestClient(TestServer(application))
    await test_client.start_server()
    try:
        # The catch-all dialog handler answers instead, so neither the page nor
        # the metrics behind it are reachable.
        assert "WWPS status" not in await (await test_client.get("/dashboard")).text()
        assert "series" not in await (await test_client.get("/dashboard/data")).text()
    finally:
        await test_client.close()


def test_attacker_controlled_fields_are_escaped_before_rendering():
    # Both fields carry the request path, which anybody can choose.
    page = wwps_app.dashboard.PAGE
    assert "esc(e.path)" in page
    assert "esc(e.message)" in page
    assert "+ e.message +" not in page


@pytest.mark.asyncio
async def test_a_hostile_path_reaches_the_snapshot_as_data_not_markup(client):
    # The endpoint table and the event log both carry the request path, and the
    # dashboard is where an operator types the admin token.
    metrics.reset()
    metrics.record_request('/<img src=x onerror="alert(1)">', 1.0, True)
    metrics.event("critical", '</script><script>alert(1)</script>')
    payload = await (await client.get("/dashboard/data", headers=HEADER)).json()
    assert payload["endpoints"][0]["path"] == '/<img src=x onerror="alert(1)">'
    assert "<script>" in payload["events"][0]["message"]
    # The page must escape both before writing them into innerHTML.
    page = wwps_app.dashboard.PAGE
    assert "function esc(s)" in page
    assert page.count("esc(e.path)") == 1
    assert page.count("esc(e.message)") == 1
