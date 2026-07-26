from __future__ import annotations

import json
import os
import sys

supabase_key: str | None = None
supabase_url: str | None = None
postgres_connection_string: str | None = None
max_connections: int = 1500
max_cached_accounts: int = 2000
is_data_download_from_supabase: bool = False
data_download_url: str | None = None
game_version: str | None = None
email_for_auth_messages: str | None = None
app_password_for_auth_messages: str | None = None
server_name: str | None = None
is_wibwob: bool = False
port: int = 8080
log_level: str = "INFO"
enforce_account_ownership: bool = True
validate_befriend: bool = True
max_score_per_second: int = 20_000
dashboard_enabled: bool = True
dashboard_token: str | None = None
admin_token: str | None = None
public_url: str | None = None
trust_proxy_headers: bool = False
rate_limit_enabled: bool = True
rate_limit_burst: int = 60
rate_limit_per_minute: int = 300
rate_limit_auth_per_minute: int = 5
max_gdkeys_per_device: int = 3

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(ROOT_DIR, "Resources")
DATA_DOWNLOAD_DIR = os.path.join(ROOT_DIR, "dataDownload")

ENV_PREFIX = "WWPS_"

# setting name -> (attribute, kind). Every setting can also be given as
# WWPS_<UPPER_SNAKE_CASE_OF_SETTING>, which wins over the file.
SETTINGS: dict[str, tuple[str, str]] = {
    "SupabaseKey": ("supabase_key", "str"),
    "SupabaseURL": ("supabase_url", "str"),
    "PostgresConnectionString": ("postgres_connection_string", "str"),
    "MaxConnections": ("max_connections", "int"),
    "MaxCachedAccounts": ("max_cached_accounts", "int"),
    "GameVersion": ("game_version", "str"),
    "ServerName": ("server_name", "str"),
    "EmailForAuthMessages": ("email_for_auth_messages", "str"),
    "AppPasswordForAuthMessages": ("app_password_for_auth_messages", "str"),
    "Port": ("port", "int"),
    "LogLevel": ("log_level", "str"),
    "EnforceAccountOwnership": ("enforce_account_ownership", "bool"),
    "ValidateBefriend": ("validate_befriend", "bool"),
    "MaxScorePerSecond": ("max_score_per_second", "int"),
    "DashboardEnabled": ("dashboard_enabled", "bool"),
    "DashboardToken": ("dashboard_token", "str"),
    "AdminToken": ("admin_token", "str"),
    "PublicUrl": ("public_url", "str"),
    "TrustProxyHeaders": ("trust_proxy_headers", "bool"),
    "RateLimitEnabled": ("rate_limit_enabled", "bool"),
    "RateLimitBurst": ("rate_limit_burst", "int"),
    "RateLimitPerMinute": ("rate_limit_per_minute", "int"),
    "RateLimitAuthPerMinute": ("rate_limit_auth_per_minute", "int"),
    "MaxGdkeysPerDevice": ("max_gdkeys_per_device", "int"),
}

_DEFAULTS = {
    "max_connections": 1500,
    "max_cached_accounts": 2000,
    "port": 8080,
    "log_level": "INFO",
    "enforce_account_ownership": True,
    "validate_befriend": True,
    "max_score_per_second": 20_000,
    "dashboard_enabled": True,
    "trust_proxy_headers": False,
    "rate_limit_enabled": True,
    "rate_limit_burst": 60,
    "rate_limit_per_minute": 300,
    "rate_limit_auth_per_minute": 5,
    "max_gdkeys_per_device": 3,
}


class ConfigError(Exception):
    pass


def _env_name(setting: str) -> str:
    out = []
    for i, char in enumerate(setting):
        if char.isupper() and i and not setting[i - 1].isupper():
            out.append("_")
        out.append(char.upper())
    return ENV_PREFIX + "".join(out)


def _env_value(setting: str):
    value = os.environ.get(_env_name(setting))
    if value is None or value == "":
        return None
    return value


def static_init(path: str | None = None):
    global is_data_download_from_supabase, data_download_url, is_wibwob

    path = path or os.environ.get(ENV_PREFIX + "CONFIG_FILE") or os.path.join(
        ROOT_DIR, "appsettings.json")

    settings: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError as ex:
                raise ConfigError(f"{path} is not valid JSON: {ex}") from ex
    elif not any(_env_value(name)
                 for name in (*SETTINGS, "IsWibWob", "DataDownloadURL")):
        raise ConfigError(
            f"no configuration found: {path} does not exist and no "
            f"{ENV_PREFIX}* environment variables are set")

    for name, (attribute, kind) in SETTINGS.items():
        raw = _env_value(name)
        if raw is None:
            raw = settings.get(name)
        default = _DEFAULTS.get(attribute)
        if kind == "int":
            globals()[attribute] = _try_int(raw, default if default is not None else 0)
        elif kind == "bool":
            globals()[attribute] = _try_bool(raw, bool(default))
        else:
            value = raw if raw not in (None, "") else default
            globals()[attribute] = value

    is_wib = _env_value("IsWibWob")
    if is_wib is None:
        is_wib = settings.get("IsWibWob")
    if isinstance(is_wib, bool):
        is_wibwob = is_wib
    elif isinstance(is_wib, str) and is_wib.lower() in ("true", "false"):
        is_wibwob = is_wib.lower() == "true"
    else:
        raise ConfigError(
            "'IsWibWob' must be set to true or false "
            f"(in {os.path.basename(path)} or {_env_name('IsWibWob')})")

    ddl = _env_value("DataDownloadURL")
    if ddl is None:
        ddl = settings.get("DataDownloadURL")
    is_data_download_from_supabase = str(ddl) == "0"
    data_download_url = None if is_data_download_from_supabase else ddl

    validate()


def validate():
    problems = []
    if not postgres_connection_string:
        problems.append(
            "PostgresConnectionString is required "
            f"(or {_env_name('PostgresConnectionString')})")
    if port < 1 or port > 65535:
        problems.append(f"Port {port} is out of range")
    if max_cached_accounts < 1:
        problems.append("MaxCachedAccounts must be at least 1")
    if max_score_per_second < 1:
        problems.append("MaxScorePerSecond must be at least 1")
    if email_for_auth_messages and not app_password_for_auth_messages:
        problems.append(
            "EmailForAuthMessages is set but AppPasswordForAuthMessages is empty")
    if public_url and not public_url.startswith(("http://", "https://")):
        problems.append("PublicUrl must start with http:// or https://")
    if problems:
        raise ConfigError("; ".join(problems))


def dashboard_available() -> bool:
    return dashboard_enabled and bool(dashboard_token)


def load_or_exit(path: str | None = None):
    try:
        static_init(path)
    except ConfigError as ex:
        print(f"Configuration error: {ex}", file=sys.stderr)
        raise SystemExit(1) from ex


def _try_bool(v, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "1", "yes", "on"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("false", "0", "no", "off"):
        return False
    return default


def _try_int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
