from __future__ import annotations

import asyncio
import json
import secrets
import uuid
import zlib
from collections import defaultdict

import asyncpg

from . import config


class TableNotFoundError(Exception):
    pass


class ServerFullError(Exception):
    pass


class Account:
    def __init__(self):
        self.gdkey: str | None = None
        self.character_id: str | None = None
        self.udkey: str | None = None
        self.user_id: str | None = None
        self.ywp_user_tables: dict | None = None
        self.last_login_time: str | None = None
        self.start_date: int = 0
        self.opening_tutorial_flag: bool = False
        self.is_dirty: bool = False


_pool: asyncpg.Pool | None = None
_account_cache: dict[str, Account] = {}
_account_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_device_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_flush_task: asyncio.Task | None = None


async def initialize():
    global _pool, _flush_task
    try:
        _pool = await asyncpg.create_pool(config.postgres_connection_string)
    except Exception:
        print("Couldn't create postgres data source.")
        raise SystemExit(1)
    _flush_task = asyncio.create_task(_flush_loop())
    print("db service started")


async def _flush_loop():
    try:
        while True:
            await asyncio.sleep(60)
            await _flush_all_dirty_accounts()
    except asyncio.CancelledError:
        print("bg flush stopped gracefully")
        raise
    except Exception as ex:
        print(f"Error in background flush loop: {ex}")


async def _flush_all_dirty_accounts():
    await asyncio.gather(*(_flush_account(gdkey) for gdkey in list(_account_cache.keys())))


async def _flush_account(gdkey: str):
    account = _account_cache.get(gdkey)
    if account is None:
        return
    async with _account_locks[gdkey]:
        if account.is_dirty:
            account.is_dirty = False
            try:
                await _update_account_no_lock(account)
                print(f"Saved account. gdkey:{gdkey}")
            except Exception as ex:
                account.is_dirty = True
                print(f"Failed to flush account {gdkey}: {ex}")
        else:
            _account_cache.pop(gdkey, None)


async def shutdown():
    if _flush_task:
        _flush_task.cancel()
    await _flush_all_dirty_accounts()


def _throw_if_cache_full():
    if len(_account_cache) >= config.max_cached_accounts:
        raise ServerFullError()


async def get_account_from_gdkey(gdkey: str) -> Account | None:
    acc = _account_cache.get(gdkey)
    if acc is not None:
        return acc
    _throw_if_cache_full()
    row = await _pool.fetchrow(
        "SELECT gdkey, character_id, udkey, user_id, ywp_user_tables, last_lgn_time, "
        "start_date, opening_tutorial_flag FROM account WHERE gdkey = $1", gdkey)
    if row is None:
        return None
    account = _read_account(row)
    _account_cache[gdkey] = account
    return account


def _read_account(row) -> Account:
    acc = Account()
    acc.gdkey = row["gdkey"]
    acc.character_id = row["character_id"]
    acc.udkey = row["udkey"]
    acc.user_id = row["user_id"]
    tables_json = row["ywp_user_tables"]
    acc.ywp_user_tables = json.loads(tables_json) if tables_json else None
    acc.last_login_time = row["last_lgn_time"]
    try:
        acc.start_date = int(row["start_date"]) if row["start_date"] else 0
    except (TypeError, ValueError):
        acc.start_date = 0
    acc.opening_tutorial_flag = bool(row["opening_tutorial_flag"])
    return acc


async def new_device(udkey: str | None = None) -> str:
    if udkey is None:
        udkey = str(uuid.uuid4())
    return await _pool.fetchval(
        "INSERT INTO device (udkey, gdkeys) VALUES ($1, $2) RETURNING udkey", udkey, [])


async def is_device_exists(udkey: str) -> bool:
    count = await _pool.fetchval("SELECT COUNT(*) FROM device WHERE udkey = $1", udkey)
    return count > 0


def _generate_friend_code() -> str:
    letters = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(letters[secrets.randbits(8) % len(letters)] for _ in range(8))


async def new_account() -> str:
    _throw_if_cache_full()
    fc = _generate_friend_code()
    acc = Account()
    acc.gdkey = str(uuid.uuid4())
    acc.ywp_user_tables = {}
    acc.last_login_time = ""
    acc.character_id = fc
    acc.user_id = str(zlib.crc32(fc.encode("utf-8")) & 0xFFFFFFFF)
    await _pool.execute(
        "INSERT INTO account (gdkey, character_id, udkey, user_id, ywp_user_tables, "
        "last_lgn_time, start_date, opening_tutorial_flag) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
        acc.gdkey, acc.character_id, acc.udkey, acc.user_id,
        json.dumps(acc.ywp_user_tables), acc.last_login_time,
        str(acc.start_date), acc.opening_tutorial_flag)
    _account_cache[acc.gdkey] = acc
    return acc.gdkey


async def set_ywp_user(gdkey: str, table_id: str, data):
    account = await get_account_from_gdkey(gdkey)
    async with _account_locks[gdkey]:
        account.ywp_user_tables[table_id] = data
        account.is_dirty = True


async def set_ywp_user_dict(gdkey: str, data: dict):
    account = await get_account_from_gdkey(gdkey)
    async with _account_locks[gdkey]:
        account.ywp_user_tables.update(data)
        account.is_dirty = True


async def set_entire_user_data(gdkey: str, data: dict):
    account = await get_account_from_gdkey(gdkey)
    async with _account_locks[gdkey]:
        account.ywp_user_tables = data
        account.is_dirty = True


async def delete_user(udkey: str, gdkey: str):
    await _remove_gdkey_from_udkey(udkey, gdkey)
    async with _account_locks[gdkey]:
        await _pool.execute("DELETE FROM account WHERE gdkey = $1", gdkey)
        _account_cache.pop(gdkey, None)


async def _remove_gdkey_from_udkey(udkey: str, gdkey: str):
    async with _device_locks[udkey]:
        await _pool.execute(
            "UPDATE device SET gdkeys = array_remove(gdkeys, $1) WHERE udkey = $2",
            gdkey, udkey)


async def get_ywp_user(gdkey: str, table_id: str):
    account = await get_account_from_gdkey(gdkey)
    if account is None:
        return None
    return account.ywp_user_tables.get(table_id)


async def delete_ywp_user(gdkey: str, table_id: str):
    account = await get_account_from_gdkey(gdkey)
    async with _account_locks[gdkey]:
        account.ywp_user_tables.pop(table_id, None)
        account.is_dirty = True


async def get_entire_user_data(gdkey: str) -> dict:
    account = await get_account_from_gdkey(gdkey)
    return account.ywp_user_tables


async def get_gdkey_from_character_id(char_id: str) -> str:
    gdkey = await _pool.fetchval(
        "SELECT gdkey FROM account WHERE character_id = $1", char_id)
    return gdkey or ""


async def get_gdkey_from_user_id(user_id: str) -> str:
    gdkey = await _pool.fetchval("SELECT gdkey FROM account WHERE user_id = $1", user_id)
    return gdkey or ""


async def get_last_login_time(gdkey: str) -> str | None:
    account = await get_account_from_gdkey(gdkey)
    return account.last_login_time if account else None


async def transfer_gdkeys(udkey_from: str, udkey_to: str):
    first_key, second_key = sorted((udkey_from, udkey_to))
    async with _device_locks[first_key]:
        ctx = _device_locks[second_key] if second_key != first_key else None
        if ctx:
            await ctx.acquire()
        try:
            async with _pool.acquire() as conn:
                async with conn.transaction():
                    from_gdkeys = await conn.fetchval(
                        "SELECT gdkeys FROM device WHERE udkey = $1", udkey_from)
                    to_gdkeys = await conn.fetchval(
                        "SELECT gdkeys FROM device WHERE udkey = $1", udkey_to)
                    if from_gdkeys is None:
                        raise Exception(f"Device {udkey_from} not found")
                    if to_gdkeys is None:
                        raise Exception(f"Device {udkey_to} not found")
                    new_to = []
                    for gdkey in from_gdkeys:
                        if gdkey not in new_to:
                            new_to.append(gdkey)
                    await conn.execute(
                        "UPDATE device SET gdkeys = $1 WHERE udkey = $2", new_to, udkey_to)
                    await conn.execute(
                        "UPDATE device SET gdkeys = $1 WHERE udkey = $2", [], udkey_from)
        finally:
            if ctx:
                ctx.release()


async def get_data_by_mail(email: str) -> dict | None:
    row = await _pool.fetchrow(
        'SELECT mail, "currentUdkey" FROM mail WHERE mail = $1', email)
    if row is None:
        return None
    return {"mail": row["mail"], "currentUdkey": row["currentUdkey"]}


async def add_or_edit_email(email: str, udkey: str):
    await _pool.execute(
        'INSERT INTO mail (mail, "currentUdkey") VALUES ($1, $2) '
        'ON CONFLICT (mail) DO UPDATE SET "currentUdkey" = EXCLUDED."currentUdkey"',
        email, udkey)


async def get_gdkeys_from_udkey(udkey: str) -> list[str]:
    gdkeys = await _pool.fetchval("SELECT gdkeys FROM device WHERE udkey = $1", udkey)
    if gdkeys is not None:
        for gdkey in gdkeys:
            account = await get_account_from_gdkey(gdkey)
            if account and not account.udkey:
                async with _account_locks[gdkey]:
                    account.udkey = udkey
                    account.is_dirty = True
    return list(gdkeys) if gdkeys is not None else []


async def add_account_to_device(udkey: str, gdkey: str):
    async with _device_locks[udkey]:
        await _pool.execute(
            "UPDATE device SET gdkeys = array_append(gdkeys, $1) WHERE udkey = $2",
            gdkey, udkey)


async def update_account(account: Account):
    async with _account_locks[account.gdkey]:
        await _update_account_no_lock(account)


async def _update_account_no_lock(account: Account):
    await _pool.execute(
        "UPDATE account SET character_id = $1, udkey = $2, user_id = $3, "
        "ywp_user_tables = $4, last_lgn_time = $5, start_date = $6, "
        "opening_tutorial_flag = $7 WHERE gdkey = $8",
        account.character_id, account.udkey, account.user_id,
        json.dumps(account.ywp_user_tables) if account.ywp_user_tables is not None else None,
        account.last_login_time, str(account.start_date),
        account.opening_tutorial_flag, account.gdkey)
