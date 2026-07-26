from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from wwps import auth


def _pend(code: int, email: str = "player@example.com", is_link: bool = True,
          udkey: str = "dev-1", minutes: int = 15):
    auth.code_cache[code] = (
        email, is_link, udkey,
        datetime.now(UTC) + timedelta(minutes=minutes))


def test_a_fresh_code_is_redeemed_once():
    _pend(123456)
    assert auth.redeem(123456, "dev-1") == ("player@example.com", True)
    # A consumed code cannot be replayed.
    assert auth.redeem(123456, "dev-1") is None


def test_an_expired_code_is_refused():
    _pend(123456, minutes=-1)
    assert auth.redeem(123456, "dev-1") is None
    assert 123456 not in auth.code_cache


def test_a_code_belongs_to_one_device():
    _pend(123456, udkey="dev-1")
    assert auth.redeem(123456, "dev-2") is None
    # Still redeemable by the device it was issued for.
    assert auth.redeem(123456, "dev-1") is not None


def test_expired_codes_are_swept():
    _pend(111111, minutes=-1)
    _pend(222222, minutes=10)
    auth.cleanup_expired_codes()
    assert 111111 not in auth.code_cache
    assert 222222 in auth.code_cache


def test_attempts_lock_out_after_five_tries():
    key = "device:dev-1"
    for _ in range(auth.MAX_ATTEMPTS):
        assert auth.attempts_left(key) > 0
        auth.record_attempt(key)
    assert auth.attempts_left(key) == 0
    auth.clear_attempts(key)
    assert auth.attempts_left(key) == auth.MAX_ATTEMPTS


def test_codes_are_six_digits_and_unique():
    codes = set()
    for _ in range(200):
        code = auth._new_code()
        assert 100000 <= code <= 999999
        _pend(code)
        codes.add(code)
    assert len(codes) == 200


@pytest.mark.parametrize("address", [
    "player@example.com",
    "first.last+tag@sub.example.co.uk",
])
def test_valid_addresses(address):
    assert auth.is_valid_email(address)


@pytest.mark.parametrize("address", [
    "",
    "no-at-sign",
    "player@example",
    "player@example.com\nBcc: victim@example.com",
    "player@example.com\r\nSubject: spam",
    "a" * 300 + "@example.com",
])
def test_rejected_addresses(address):
    # A newline here would inject headers into the outgoing message.
    assert not auth.is_valid_email(address)
