# Data model

## PostgreSQL schema

Three tables, defined in `Database/schema.sql`.

```sql
account (gdkey PK, ywp_user_tables jsonb, last_lgn_time, opening_tutorial_flag,
         start_date, character_id UNIQUE, user_id UNIQUE, udkey)
device  (udkey PK, gdkeys text[])
mail    (mail PK, "currentUdkey")
```

- **gdkey** — a save file. One per character. Generated as a UUID.
- **udkey** — a device. Owns up to three gdkeys, which is what the client's
  account-select screen lists.
- **character_id** — the eight-character friend code (`abcdefghijklmnopqrstuvwxyz0123456789`).
- **user_id** — CRC32 of the friend code, as a decimal string. This is the id
  other players see and the one friend requests are addressed to.
- **ywp_user_tables** — the entire player save, as one JSONB document. Every
  `ywp_user_*` table plus a handful of server-private keys lives in here.

The `mail` table only maps an email address to the device that currently owns the
save, which is all the linking flow needs.

## The account cache

`wwps/user_data.py` never reads a player's tables from PostgreSQL more than once
per session. `get_account_from_gdkey` loads the row, builds an `Account` object,
and stores it in `_account_cache`. Every mutation goes to that object and sets
`is_dirty = True`.

A background task started at server startup runs every 60 seconds and, for each
cached account:

- if it is dirty, write it back to PostgreSQL and clear the flag;
- if it is not dirty, evict it from the cache.

So an idle player is dropped after at most two flush cycles, and an active player
stays resident. `shutdown()` runs the same flush once more, so a clean stop
persists everything.

Concurrency is handled with per-key `asyncio.Lock`s: one per gdkey for account
mutations, one per udkey for device mutations. `transfer_gdkeys` takes both
device locks in sorted order to avoid deadlock, and does the two UPDATEs inside a
single transaction so a crash cannot leave a half-moved save.

`MaxCachedAccounts` bounds the cache. When it is full, loading a not-yet-cached
player raises `ServerFullError`, which `server_full_middleware` turns into a
"The server is full" dialog with HTTP 503. Already-cached players are unaffected.

## Server-private keys

Besides the game's own `ywp_user_*` tables, the save document holds keys the
client never sees:

| Key | Meaning |
| --- | --- |
| `ywp_user_requestid` | The battle session token (see protocol.md) |
| `last_hitodama_recover` | Timestamp of the last spirit regeneration tick |
| `lastShopResetDate` | `YYYYMMDD` of the last daily shop stock reset |
| `lastAdditionDate` | `YYYYMMDD` of the last shrine visit |
| `ywp_user_addition` | True if the current shrine bonus is the super one |
| `last_enemy` | The enemy list sent by `gameStart`, checked again at `gameEnd` |
| `ywp_pending_score` | Score-attack result waiting to be picked up by ranking |
| `opening_tutorial_flg` | Whether the opening tutorial is done |

`last_enemy` is the anti-cheat check: `gameEnd` rejects a result that reports
defeating a Yo-kai that was never on the stage.

## The table format

Most player tables are not JSON. They are a flat string: rows separated by `*`,
columns separated by `|`. A few master tables use `^` as the column separator
instead (Puni's `ywp_mst_stage_condition`), and some carry a `prefix:` before the
data.

```
2157000|1|0|120|45|1000|0|0|0|1749900000000|0*2213000|3|...
```

`wwps/table_parser.py` implements two views over that format:

- **`TableParser`** — raw. `table` is a list of lists of strings. Used where the
  server only needs to read or copy a column.
- **`TypedTableParser`** — typed. Each row is mapped positionally onto a class
  from `wwps/rows.py`, so `items[0].Level` works. Conversion failures are
  swallowed per field, matching the C# behaviour of skipping bad cells rather
  than rejecting the row.

Because the mapping is positional, **the field order in `rows.py` is the wire
format**. Reordering a row class silently corrupts saves. The order was taken
from the C# property declaration order, which is what the original
reflection-based parser used.

`parser_for(RowClass, src)` is the shortcut used throughout the handlers.

### `find_index`

`find_index(identifiers)` looks up a row by the values it contains, in any
column. It intersects the candidate sets for each identifier and returns as soon
as exactly one candidate remains; a missing identifier returns `-1`. The
intersection step stops at the first match rather than computing a full set
intersection — this is faithful to the original and works because callers pass
identifiers that are unique in practice (usually a single id).

### Serialization

`str(parser)` re-renders the table. The typed parser rebuilds its raw rows from
`items` on every render, under a lock, because a shared parser (for example the
static mission master table) can otherwise be re-rendered concurrently and see a
half-rebuilt list. Leading and trailing `*` are stripped.

## Version-dependent lists

Two structures changed shape between Puni Puni and Wibble Wobble:

| Structure | Puni Puni | Wibble Wobble |
| --- | --- | --- |
| `ywp_user_tutorial_list` | pipe table | JSON array |
| `lotYoukaiInfoList` | pipe table | JSON array |

`dto.TutorialList` and `dto.LotYoukaiInfoList` accept either form on input and
serialize according to `config.is_wibwob` on output.

## `ywp_user_data`

The player's core record, in `wwps/ywp_user_data.py`. Attribute names are the
wire names (`freeHitodama`, `ymoney`, `nowStageId`, …) so `to_dict()` is a
straight copy.

New accounts start with: 5 free hitodama, 0 paid hitodama, 3000 Y-Money, stage
1001001, watch 10101, partner Yo-kai 2235000.

### Hitodama recovery

`hitodama_recover()` runs whenever the record is loaded. Free spirits regenerate
one per 900 seconds up to a cap of 5, counting paid spirits toward the cap. The
timestamp lives in `last_hitodama_recover`. If the player is still below the cap
after applying the recovered spirits, the stored timestamp is rewound by the
leftover partial interval, so no progress toward the next spirit is lost.
`hitodamaRecoverSec` in the response is the countdown the client displays.
