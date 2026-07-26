# Configuration

Deployment itself is covered in [deployment.md](deployment.md).

## Where settings come from

Settings are read once at startup, in this order, last one winning:

1. `appsettings.json` in the repository root. Copy `appsettings.example.json`
   and fill it in.
2. Environment variables. Every setting has a `WWPS_` name in upper snake case:
   `PostgresConnectionString` becomes `WWPS_POSTGRES_CONNECTION_STRING`,
   `IsWibWob` becomes `WWPS_IS_WIB_WOB`, `AdminToken` becomes
   `WWPS_ADMIN_TOKEN`. Empty values are treated as unset.

The file is optional when the environment supplies what is needed, which is how
the Docker image is configured — see `.env.example`. Point the server at a
different file with `WWPS_CONFIG_FILE`.

Startup stops with a readable message when the configuration cannot work: no
database DSN, a port out of range, `IsWibWob` missing, a `PublicUrl` without a
scheme, or a mail address without its app password.

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
| `MaxScorePerSecond` | no (20000) | Score ceiling per elapsed battle second, for the anti-cheat check. Raise it if honest players trip it; the old default of a million accepted anything. |
| `MaxGdkeysPerDevice` | no (3) | Saves one device may create. This is what the client is told, and now what the server enforces. |
| `DashboardEnabled` | no (true) | Serve the status dashboard on `/dashboard`. |
| `DashboardToken` | no | Required for the dashboard to be served at all. Sent as the `X-Dashboard-Token` header. |
| `AdminToken` | no | Required for the admin API to be served at all. Sent as the `X-Admin-Token` header. |
| `PublicUrl` | no | The URL players reach this server on, e.g. `https://wwps.example.com`. Handed to the client as its asset and API base. Set this whenever a proxy or a domain is in front. |
| `TrustProxyHeaders` | no (false) | Believe `X-Forwarded-Proto`, `X-Forwarded-Host` and `X-Forwarded-For`. Only turn this on when a proxy you control sets them; otherwise a forged header decides where clients send their traffic. |
| `RateLimitEnabled` | no (true) | Per-client token buckets. Turn off only on a closed LAN. |
| `RateLimitPerMinute` | no (300) | Gameplay budget per client. |
| `RateLimitBurst` | no (60) | How much of that budget can be spent at once. |
| `RateLimitAuthPerMinute` | no (5) | Budget for `/auth/*`, `/l5id/*`, `/admin/*`, `serialConfirm` and account creation. |

`appsettings.json` and `.env` are both gitignored because they hold
credentials. Generate the two tokens with `openssl rand -hex 32`;
`scripts/setup.sh` does it for you.

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
DATABASE_URL=postgresql://... make schema
```

That applies `Database/schema.sql` and everything in `Database/migrations/`.
Both are idempotent, so running them again is safe. Under Docker the entrypoint
does it on every boot. See `docs/data-model.md`.

## Running

```bash
make install
make run
```

Binds `0.0.0.0:8080`. There is no TLS termination in-process; put a reverse
proxy in front and set `PublicUrl`. See [deployment.md](deployment.md).

## Operational notes

- **Saves are flushed every 60 seconds**, and on clean shutdown. `SIGKILL` loses
  at most one flush interval of progress.
- **Cache eviction is lazy but bounded**: an account that stops being modified is
  dropped on the next flush, and when the cache is full the least recently used
  clean saves are evicted before any player is refused. `MaxCachedAccounts`
  bounds roughly the number of players active within the last two minutes, not
  total registrations.
- **Logs go to stdout** through the standard logging module. Save keys, device
  ids and addresses are truncated so a log file is not a credential store.
- **Unimplemented endpoints are visible in-game** rather than silent, so a
  missing route shows up as a dialog naming the path.
