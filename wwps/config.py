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

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(ROOT_DIR, "Resources")
DATA_DOWNLOAD_DIR = os.path.join(ROOT_DIR, "dataDownload")


def static_init(path: str | None = None):
    global supabase_key, supabase_url, postgres_connection_string, max_connections
    global max_cached_accounts, is_data_download_from_supabase, data_download_url
    global game_version, email_for_auth_messages, app_password_for_auth_messages
    global server_name, is_wibwob

    path = path or os.path.join(ROOT_DIR, "appsettings.json")
    with open(path, encoding="utf-8") as f:
        config = json.load(f)

    supabase_key = config.get("SupabaseKey")
    supabase_url = config.get("SupabaseURL")
    postgres_connection_string = config.get("PostgresConnectionString")
    max_connections = _try_int(config.get("MaxConnections"), 1500)
    max_cached_accounts = _try_int(config.get("MaxCachedAccounts"), 2000)
    game_version = config.get("GameVersion")
    server_name = config.get("ServerName")
    email_for_auth_messages = config.get("EmailForAuthMessages")
    app_password_for_auth_messages = config.get("AppPasswordForAuthMessages")

    is_wib = config.get("IsWibWob")
    if isinstance(is_wib, bool):
        is_wibwob = is_wib
    elif isinstance(is_wib, str) and is_wib.lower() in ("true", "false"):
        is_wibwob = is_wib.lower() == "true"
    else:
        print("Please specify 'IsWibWob' as true or false in appsettings.", file=sys.stderr)
        raise SystemExit(1)

    ddl = config.get("DataDownloadURL")
    if str(ddl) == "0":
        is_data_download_from_supabase = True
    else:
        data_download_url = ddl


def _try_int(v, default: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default
