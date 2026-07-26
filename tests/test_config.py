from __future__ import annotations

import json

import pytest

from wwps import config


@pytest.fixture
def settings_file(tmp_path):
    path = tmp_path / "appsettings.json"
    path.write_text(json.dumps({
        "PostgresConnectionString": "postgresql://localhost/wwps",
        "IsWibWob": True,
        "Port": 8080,
        "AdminToken": "from-the-file",
    }))
    return str(path)


def test_the_file_is_read(settings_file):
    config.static_init(settings_file)
    assert config.admin_token == "from-the-file"
    assert config.port == 8080


def test_the_environment_wins_over_the_file(settings_file, monkeypatch):
    monkeypatch.setenv("WWPS_ADMIN_TOKEN", "from-the-environment")
    monkeypatch.setenv("WWPS_PORT", "9000")
    config.static_init(settings_file)
    assert config.admin_token == "from-the-environment"
    assert config.port == 9000


def test_an_empty_variable_is_treated_as_unset(settings_file, monkeypatch):
    monkeypatch.setenv("WWPS_ADMIN_TOKEN", "")
    config.static_init(settings_file)
    assert config.admin_token == "from-the-file"


def test_the_file_is_optional_when_the_environment_is_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("WWPS_POSTGRES_CONNECTION_STRING", "postgresql://localhost/x")
    monkeypatch.setenv("WWPS_IS_WIB_WOB", "false")
    config.static_init(str(tmp_path / "missing.json"))
    assert config.is_wibwob is False
    assert config.postgres_connection_string == "postgresql://localhost/x"


def test_environment_names(tmp_path):
    assert config._env_name("PostgresConnectionString") == \
        "WWPS_POSTGRES_CONNECTION_STRING"
    assert config._env_name("SupabaseURL") == "WWPS_SUPABASE_URL"
    assert config._env_name("IsWibWob") == "WWPS_IS_WIB_WOB"
    assert config._env_name("AdminToken") == "WWPS_ADMIN_TOKEN"


@pytest.mark.parametrize("overrides, expected", [
    ({"PostgresConnectionString": ""}, "PostgresConnectionString is required"),
    ({"Port": 99999}, "out of range"),
    ({"PublicUrl": "wwps.example.com"}, "http://"),
    ({"EmailForAuthMessages": "a@b.com"}, "AppPasswordForAuthMessages"),
    ({"MaxScorePerSecond": 0}, "MaxScorePerSecond"),
])
def test_unusable_configurations_are_refused(tmp_path, overrides, expected):
    settings = {
        "PostgresConnectionString": "postgresql://localhost/wwps",
        "IsWibWob": True,
    }
    settings.update(overrides)
    path = tmp_path / "appsettings.json"
    path.write_text(json.dumps(settings))
    with pytest.raises(config.ConfigError) as error:
        config.static_init(str(path))
    assert expected in str(error.value)


def test_a_missing_iswibwob_is_refused(tmp_path):
    path = tmp_path / "appsettings.json"
    path.write_text(json.dumps(
        {"PostgresConnectionString": "postgresql://localhost/wwps"}))
    with pytest.raises(config.ConfigError) as error:
        config.static_init(str(path))
    assert "IsWibWob" in str(error.value)


def test_broken_json_is_reported_as_such(tmp_path):
    path = tmp_path / "appsettings.json"
    path.write_text("{ not json")
    with pytest.raises(config.ConfigError) as error:
        config.static_init(str(path))
    assert "not valid JSON" in str(error.value)


def test_the_dashboard_needs_a_token_to_be_available(settings_file, monkeypatch):
    monkeypatch.setenv("WWPS_DASHBOARD_ENABLED", "true")
    config.static_init(settings_file)
    assert config.dashboard_available() is False
    monkeypatch.setenv("WWPS_DASHBOARD_TOKEN", "secret")
    config.static_init(settings_file)
    assert config.dashboard_available() is True
