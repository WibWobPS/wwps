# Configuration and deployment

## `appsettings.json`

Loaded once at startup by `config.static_init()` from the repository root. Copy
`appsettings.example.json` and fill it in.

| Key | Required | Meaning |
| --- | --- | --- |
| `PostgresConnectionString` | yes | asyncpg DSN, e.g. `postgresql://user:pass@host:5432/wwps`. A connection failure at startup exits the process. |
| `IsWibWob` | yes | `true` for Wibble Wobble, `false` for Puni Puni. Anything else is fatal. Selects the gacha handler, the tutorial/lot list encoding and the gacha reroll mode. |
| `GameVersion` | yes | The only `appVer` accepted by `init.nhn`; every other client version gets a "wrong version" dialog. |
| `DataDownloadURL` | yes | Asset server URL handed to the client as `imgServer`. The literal value `0` selects Supabase storage, which is not implemented. |
| `ServerName` | yes | Shown in dialog titles, including the unimplemented-endpoint fallback. |
| `MaxConnections` | no (1500) | Listen backlog. |
| `MaxCachedAccounts` | no (2000) | Account cache ceiling. Once reached, players who are not already cached get a "server is full" dialog. |
| `EmailForAuthMessages` | only for linking | Gmail account used to send the six-digit codes. |
| `AppPasswordForAuthMessages` | only for linking | Gmail app password for that account. |
| `SupabaseKey`, `SupabaseURL` | no | Read into config but unused; the Supabase storage path was never implemented. |
| `Port` | no (8080) | Listen port. |
| `LogLevel` | no (INFO) | Root log level: DEBUG, INFO, WARNING, ERROR. |
| `EnforceAccountOwnership` | no (true) | Reject requests whose device does not own the named save. Leave on. |
| `ValidateBefriend` | no (true) | Reject befriends that were never rolled by `gameStart`. |
| `MaxScorePerSecond` | no (1000000) | Score ceiling per elapsed battle second, for the anti-cheat check. |
| `DashboardEnabled` | no (true) | Serve the status dashboard on `/dashboard`. |
| `DashboardToken` | no | If set, the dashboard requires `?token=…` or an `X-Dashboard-Token` header. |

`appsettings.json` is gitignored because it holds credentials.

## Game data (`Resources/`)

The server needs the game's master tables and a few WWPS-specific data files.
Each is a `.txt` file whose name (without the extension) is the id the server
looks up. The C# build embedded these into the assembly and they were never
committed to the original repository, so they must be supplied.

Broadly, three kinds of file live here:

- **Master tables** — `ywp_mst_*`, usually a JSON object with the real payload
  under `tableData` (a pipe table) or `data` (a JSON array).
- **Default user tables** — `<table>_def`, used by `createUser.nhn` to seed a new
  save. Every `ywp_user_*` name in `consts.LOGIN_TABLES_PUNI` needs one, or
  account creation fails.
- **Server-side data** — `stage_data` (enemies, first-clear rewards, tutorial and
  menu edits, alternate unlocks per stage), `gacha_pool` (crank weights, pools
  and convert items), `mission_cfg` (mission series and parameters),
  `rare_enemy`, `maps_to_add_login`, `unavailable_maps`, `map_add_tutorial`, and
  scalar values such as `mstVersionMaster`, `noticePageList`,
  `ymoneyShopSaleList`, `shopSaleList`, `hitodamaShopSaleList`,
  `responseCodeTeamEvent`, `teamEventButtonHiddenFlg`, `noticePageListFlg`.

A missing `Resources/` directory only logs a warning at startup — the server will
start and then fail per-request as handlers look tables up.

`dataDownload/help.html` is needed by `/help/inquiry/top.nhn`, the in-game
webview used for account linking.

## Database

```bash
psql "$DATABASE_URL" -f Database/schema.sql
```

Three tables, no migrations. See `docs/data-model.md`.

## Running

```bash
pip install -r requirements.txt
python -m wwps
```

Binds `0.0.0.0:8080`. There is no TLS termination in-process; the original
deployment sat behind a reverse proxy, and the client is normally redirected to
the server by DNS or a host patch.

## Operational notes

- **Saves are flushed every 60 seconds**, and on clean shutdown. `SIGKILL` loses
  at most one flush interval of progress.
- **Cache eviction is lazy**: an account that stops being modified is dropped on
  the next flush, so `MaxCachedAccounts` bounds roughly the number of players
  active within the last two minutes, not total registrations.
- **Logs go to stdout** as plain `print` calls: account flushes, mission checks,
  unknown table names, tribe-unity bonuses and stage-condition evaluations.
- **Unimplemented endpoints are visible in-game** rather than silent, so a
  missing route shows up as a dialog naming the path.
