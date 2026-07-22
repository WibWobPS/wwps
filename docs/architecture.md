# Architecture

## Overview

WWPS is a single aiohttp application. There is no ORM, no dependency injection
container and no background worker process: the whole server is one asyncio event
loop that serves encrypted HTTP requests, mutates an in-memory account cache, and
periodically flushes that cache to PostgreSQL.

```
game client
    |  HTTP POST /login.nhn   (body = base64url AES blob)
    v
aiohttp app  (wwps/app.py)
    |  rewrite_middleware        normalize the path
    |  server_full_middleware    turn ServerFullError into a 503 dialog
    v
handler  (wwps/handlers/*.py)
    |  utils.read_decrypted_request  ->  dict
    |  game_data.gamedata_cache      ->  static master tables (Resources/*.txt)
    |  user_data.get_ywp_user        ->  per-player tables (account cache)
    |  managers.*                    ->  shared game rules
    v
utils.encrypted_json(dict)  ->  base64url AES blob
```

## Module map

| Module | Responsibility |
| --- | --- |
| `wwps/app.py` | Route table, middlewares, startup/shutdown hooks, `main()` |
| `wwps/config.py` | Loads `appsettings.json` into module-level globals |
| `wwps/nhn_crypt.py` | The NHN request/response cipher |
| `wwps/utils.py` | Request decoding, response encoding, `add_tables_to_response` |
| `wwps/game_data.py` | Static master data cache, loaded from `Resources/*.txt` |
| `wwps/user_data.py` | PostgreSQL access plus the write-back account cache |
| `wwps/ywp_user_data.py` | The `ywp_user_data` table object and hitodama recovery |
| `wwps/table_parser.py` | The pipe/asterisk table format (raw and typed) |
| `wwps/rows.py` | Typed row classes; column order is the wire format |
| `wwps/dto.py` | Response envelopes and the two version-dependent list wrappers |
| `wwps/consts.py` | Table name lists and the message-box response shape |
| `wwps/managers.py` | Shared game logic used by more than one endpoint |
| `wwps/auth.py` | Email-code account linking (the custom auth flow) |
| `wwps/handlers/` | One module per endpoint family |

### Handler modules

| Module | Endpoints |
| --- | --- |
| `l5id.py` | `active`, `create_gdkey` (the Level-5 ID API the client hits before the game server) |
| `init.py` | `init`, `initBilling`, `initGacha`, `initGoku`, `initCollectMenu`, `initCrystal`, `initScoreAttack` |
| `basic.py` | `login`, `createUser`, `getMaster`, `getGdkeyAccounts`, `deleteUser`, `userInfoRefresh`, `rename`, `updateProfile`, `updateTutorialFlg`, `getL5idStatus`, `conflate` |
| `game.py` | `gameStart`, `gameEnd`, `gameRetire`, `gameContinue`, `gameUseItem`, score-attack start/end |
| `gacha.py` | `executeGacha`, `gacha`, and the crank pool roller |
| `friend.py` | `friend`, `friendSearch`, `friendRequest`, `friendRequestAccept`, `friendRequestDelete`, `friendDelete` |
| `world.py` | `map`, `mapWarp`, `mapUnLock`, `loginStamp`, `useItem`, `buyItem`, `buyHitodama`, `getMission`, `missionReward` |
| `yokai.py` | `deckEdit`, `evolveYoukai`, `releaseYoukai`, `levelLockOff` |
| `misc.py` | Watch, shrine, goku/crystal menus, ranking, present box, `serialConfirm`, the fallback handler |

## Request lifecycle in detail

1. **Path rewrite.** `rewrite_middleware` collapses repeated leading slashes and
   strips a trailing slash. The original C# server rewrote `*.nhn` to `*.nhn/`
   because ASP.NET Core treated a bare `.nhn` path as a static file request;
   aiohttp has no such behaviour, so WWPS normalizes in the opposite direction
   and both `/login.nhn` and `/login.nhn/` reach the same handler.

2. **Decryption.** `utils.read_decrypted_request` reads the whole body, runs it
   through `nhn_crypt.decrypt_request`, and parses the resulting JSON into a
   `dict`. Handlers work with raw wire keys (`level5UserId`, `stageId`, …)
   rather than typed request objects.

3. **Data access.** Static master tables come from `game_data.gamedata_cache`,
   which is a plain dict populated once at startup. Player tables come from
   `user_data`, which serves them out of the account cache.

4. **Response.** Handlers build a `dict`, usually starting from
   `dto.common_response_full()` or `dto.common_response_dict()`, then
   `utils.encrypted_json` serializes, compresses, encrypts and returns it with
   `Content-Type: application/json`.

5. **Errors.** Game-visible failures are returned as message-box responses
   (`consts.msg_box_response`) with HTTP 200 — the client renders them as an
   in-game dialog. Only malformed requests return HTTP 400 via
   `utils.bad_request()`.

## Startup and shutdown

`main()` performs three steps in order:

1. `config.static_init()` reads `appsettings.json`. A missing or non-boolean
   `IsWibWob` is fatal.
2. `game_data.init()` loads every `Resources/*.txt` file into memory, keyed by
   file name without the extension.
3. `web.run_app` starts the server; the `on_startup` hook opens the asyncpg pool
   and starts the flush loop.

On shutdown the `on_cleanup` hook cancels the flush task and writes every dirty
account back to PostgreSQL, so a clean stop never loses progress.
