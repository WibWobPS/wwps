from __future__ import annotations

import asyncio

import pytest

from wwps import metrics, validate
from wwps import user_data as manage_data

from .test_endpoints import call, client  # noqa: F401  (the fixture is reused)

__all__ = ["client"]


@pytest.fixture(autouse=True)
def real_locks(monkeypatch):
    manage_data._request_locks.clear()
    yield
    manage_data._request_locks.clear()


@pytest.mark.asyncio
async def test_parallel_purchases_each_charge_the_player(client, store):
    """Two requests for one save must not both spend the same Y-Money.

    Handlers read the balance, await, then write it back, so without the
    per-save lock both calls would see 1000 and the player would keep one
    purchase for free.
    """
    store["tables"]["gd-1"]["ywp_user_data"]["ymoney"] = 1000
    payload = {"level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 1}
    await asyncio.gather(*(call(client, "/buyHitodama.nhn", dict(payload))
                           for _ in range(5)))
    assert store["tables"]["gd-1"]["ywp_user_data"]["ymoney"] == 500
    assert store["tables"]["gd-1"]["ywp_user_data"]["hitodama"] == 3 + 5 * 6


@pytest.mark.asyncio
async def test_requests_for_different_saves_are_not_serialized(client, store):
    lock_one = manage_data.request_lock("gd-1")
    lock_two = manage_data.request_lock("gd-2")
    assert lock_one is not lock_two


@pytest.mark.asyncio
async def test_the_save_lock_is_released_after_the_response(client, store):
    await call(client, "/buyHitodama.nhn", {
        "level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 1})
    assert not manage_data.request_lock("gd-1").locked()


@pytest.mark.asyncio
async def test_the_save_lock_is_released_when_a_handler_fails(client, store):
    from .test_endpoints import _encrypt

    # goodsId 999 does not exist, so the handler returns early with a plain
    # error rather than an encrypted body.
    response = await client.post("/buyHitodama.nhn", data=_encrypt({
        "level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 999}))
    assert response.status == 400
    assert not manage_data.request_lock("gd-1").locked()


@pytest.mark.asyncio
async def test_a_quantity_that_is_not_a_number_is_a_clean_error(client, store):
    metrics.reset()
    status, body = await call(client, "/buyItem.nhn", {
        "level5UserId": "gd-1", "deviceId": "dev-1", "goodsId": 1,
        "cnt": "all of them"})
    assert status == 400
    assert body["dialogTitle"] == "Invalid request"
    assert metrics.snapshot()["counters"].get("unhandled_errors") is None


def test_req_int_bounds():
    assert validate.req_int({"n": "7"}, "n") == 7
    assert validate.req_int({}, "n", 3) == 3
    with pytest.raises(validate.InvalidRequestError):
        validate.req_int({"n": "x"}, "n")
    with pytest.raises(validate.InvalidRequestError):
        validate.req_int({"n": -1}, "n", minimum=0)
    with pytest.raises(validate.InvalidRequestError):
        validate.req_int({"n": 10}, "n", maximum=9)


def test_req_str_length_and_requirement():
    assert validate.req_str({"s": "abc"}, "s") == "abc"
    with pytest.raises(validate.InvalidRequestError):
        validate.req_str({"s": "x" * 100}, "s", max_length=10)
    with pytest.raises(validate.InvalidRequestError):
        validate.req_str({}, "s", required=True)


def test_clean_name_removes_the_table_delimiters():
    # '|' separates fields and '*' separates rows in the save format, so a name
    # carrying either would corrupt every table it is copied into.
    assert validate.clean_name("Bad|Name*Here") == "BadNameHere"
    assert validate.clean_name("drop\x00me\n") == "dropme"
    assert validate.clean_name("x" * 100) == "x" * validate.MAX_PLAYER_NAME
    assert validate.clean_name("  spaced  ") == "spaced"


def test_key_like_accepts_only_identifier_characters():
    assert validate.is_key_like("6f1e2a3b-4c5d")
    assert validate.is_key_like("dev_1")
    assert not validate.is_key_like("")
    assert not validate.is_key_like("../../etc/passwd")
    assert not validate.is_key_like("a" * 200)
