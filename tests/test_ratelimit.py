from __future__ import annotations

import pytest

from wwps import config, ratelimit


@pytest.fixture(autouse=True)
def limiter(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_enabled", True)
    ratelimit.reset()
    yield
    ratelimit.reset()


def test_a_burst_is_allowed_then_refused(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_burst", 5)
    monkeypatch.setattr(config, "rate_limit_per_minute", 60)
    assert all(ratelimit.allow("normal", "1.2.3.4", now=100.0) for _ in range(5))
    assert not ratelimit.allow("normal", "1.2.3.4", now=100.0)


def test_the_bucket_refills_over_time(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_burst", 2)
    monkeypatch.setattr(config, "rate_limit_per_minute", 60)
    for _ in range(2):
        assert ratelimit.allow("normal", "1.2.3.4", now=0.0)
    assert not ratelimit.allow("normal", "1.2.3.4", now=0.0)
    assert ratelimit.allow("normal", "1.2.3.4", now=1.0)


def test_clients_have_separate_budgets(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_burst", 1)
    assert ratelimit.allow("normal", "1.1.1.1", now=0.0)
    assert not ratelimit.allow("normal", "1.1.1.1", now=0.0)
    assert ratelimit.allow("normal", "2.2.2.2", now=0.0)


def test_authentication_paths_get_the_strict_budget(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_auth_per_minute", 3)
    for _ in range(3):
        assert ratelimit.allow("strict", "1.2.3.4", now=0.0)
    assert not ratelimit.allow("strict", "1.2.3.4", now=0.0)


def test_tier_selection():
    assert ratelimit._tier("/auth/link") == "strict"
    assert ratelimit._tier("/admin/stats") == "strict"
    assert ratelimit._tier("/l5id/api/v1/create_gdkey.nhn") == "strict"
    assert ratelimit._tier("/serialConfirm.nhn") == "strict"
    assert ratelimit._tier("/createUser.nhn") == "strict"
    assert ratelimit._tier("/gameEnd.nhn") == "normal"
    assert ratelimit._tier("/healthz") is None
    assert ratelimit._tier("/dd/help.html") is None


def test_disabling_the_limiter_allows_everything(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_enabled", False)
    monkeypatch.setattr(config, "rate_limit_burst", 1)
    assert all(ratelimit.allow("normal", "1.2.3.4", now=0.0) for _ in range(50))


def test_tracked_clients_are_swept(monkeypatch):
    monkeypatch.setattr(config, "rate_limit_burst", 1)
    for i in range(100):
        ratelimit.allow("normal", f"10.0.0.{i}", now=0.0)
    assert len(ratelimit._buckets) == 100
    # Long past the idle window, so the table empties rather than growing with
    # every address that has ever sent a request.
    ratelimit.allow("normal", "10.0.1.1", now=10_000.0)
    assert len(ratelimit._buckets) == 1


def test_forwarded_headers_are_only_believed_when_configured(monkeypatch):
    class Req:
        headers = {"X-Forwarded-For": "9.9.9.9, 10.0.0.1"}
        remote = "127.0.0.1"

    monkeypatch.setattr(config, "trust_proxy_headers", False)
    assert ratelimit.client_key(Req()) == "127.0.0.1"
    monkeypatch.setattr(config, "trust_proxy_headers", True)
    assert ratelimit.client_key(Req()) == "9.9.9.9"
