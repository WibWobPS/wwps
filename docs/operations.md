# Operations: security, logging, metrics, dashboard

This covers the operational layer added on top of the game server: the anti-abuse
checks, the logger, the metrics registry and the status dashboard.

## Security

Several classes of abuse are checked. All are on by default and each has a
config flag (`EnforceAccountOwnership`, `ValidateBefriend`, `RateLimitEnabled`).

Read the trust model in [SECURITY.md](../SECURITY.md) first: the request cipher
is obfuscation, so every check below assumes the client is hostile.

### Account ownership

`wwps/security.py` enforces that the device sending a request actually owns the
save it names. Every decrypted request runs through `enforce_ownership`
(called from `utils.read_decrypted_request`, so no handler can forget it):

- A request with no gdkey is allowed through — endpoints like `getGdkeyAccounts`
  operate on a device, not a save.
- A request with a gdkey but no device id is rejected.
- Otherwise the device's gdkey list is checked. A save the device does not own
  returns HTTP 403 with an "Authentication error" dialog.

Positive results are cached in a set and the cache is cleared whenever a save is
attached, deleted or transferred, so a freshly linked save is recognized
immediately.

Without this check, any player who learns another player's gdkey — which leaks
through `getGdkeyAccounts` and the friend system — could read and overwrite that
save. It is the single most important hardening on the server.

### Battle validation

The client reports its own battle results, so `gameEnd` cannot trust them
blindly. Two checks run before a result is accepted:

- **Elapsed time.** The `requestId` issued by `gameStart` is a millisecond
  timestamp, so the real wall-clock duration of the battle is known. A result
  whose `clearTimeSec` exceeds that duration (plus a 5s skew allowance) is
  rejected.
- **Score ceiling.** Score is capped at `MaxScorePerSecond` times the elapsed
  seconds, plus a flat grace of one million. Anything above is rejected.

A rejected result clears the session token and returns an "Invalid result"
dialog, so it cannot simply be retried.

`MaxScorePerSecond` defaults to 20000 with a flat grace of 100000. The point is
to bound what a modified client can claim, not to model perfect play, so watch
`cheat_score_cap` after a change and raise the ceiling if honest players trip
it.

### Befriend validation

`gameStart` computes and stores the befriend odds table in `last_enemy`. At
`gameEnd`, a claimed catch (`dropYoukaiFlg == 1`) is checked against that stored
table: the server reconstructs the lot pattern from the soultimate uses the
client reported, finds the matching entry, and confirms the result bit for the
food tier the player used is set. A catch that was never rolled is dropped from
the response and counted as `cheat_befriend`.

This closes the largest economy exploit: without it, sending `dropYoukaiFlg: 1`
for any on-stage enemy grants that Yo-kai unconditionally.

### One request at a time per save

Handlers read a save table, await, and write it back. Two requests naming the
same save could otherwise interleave so that both read the pre-request balance
and the second write discarded the first — a player firing parallel purchases
kept the goods and the money. `utils.read_decrypted_request` takes a per-save
lock as soon as the gdkey is known and a middleware releases it when the
response is done, so requests for one save are serialized while requests for
different saves still run concurrently.

### Rate limiting

`wwps/ratelimit.py` is a token bucket per client, with no external dependency.
Two tiers:

- **strict** (`RateLimitAuthPerMinute`, default 5/min) for `/auth/*`,
  `/l5id/*`, `/admin/*`, `serialConfirm`, `createUser` and `deleteUser` — the
  endpoints that send mail, create rows or guard operator data.
- **normal** (`RateLimitPerMinute`, default 300/min with a burst of
  `RateLimitBurst`) for gameplay.

Health probes and the static download path are exempt. A throttled request gets
`429` with `Retry-After` and increments `rate_limited`. The client key is the
peer address, or the first `X-Forwarded-For` entry when `TrustProxyHeaders` is
on — which is only honest if your proxy overwrites that header.

### Account management codes

The six-digit codes behind `/auth/link` and `/auth/restore` come from `secrets`,
expire after fifteen minutes, are consumed on use, and are bound to the device
that owns the save. Five wrong attempts lock a device out for fifteen minutes,
the pending-code table is capped, and the address is validated before any mail
is built.

## Logging

`wwps/logging_setup.py` replaces every `print` with the standard `logging`
module. `configure()` installs one colored stdout handler; `NO_COLOR` disables
color, `FORCE_COLOR` forces it, and a non-TTY (a pipe or a file) gets plain text
automatically.

The format is `time level name message`, with the level color-coded (blue info,
amber warning, red error, bright-red critical) and the module name dimmed.
`LogLevel` in the config sets the threshold. Each module gets its logger with
`logging_setup.get(__name__)`.

## Metrics

`wwps/metrics.py` is an in-process registry — no external time-series database.
`metrics_middleware` records every request's path, duration and failure. Handlers
add domain counters (`incr`), gauges (`gauge`) and notable events (`event`).

What it tracks:

- **Counters** — totals that only grow: requests, failures, logins, accounts
  created, battles started/finished, Yo-kai befriended, gacha rolls, shop
  purchases, and every rejection counter (`auth_rejected`, `cheat_score_cap`,
  `cheat_befriend`, …).
- **Gauges** — point-in-time values: accounts cached, flush duration, locks held.
- **Rolling window** — per-second request and error buckets over the last two
  minutes, for the rate chart.
- **Latency** — the last 512 samples, exposed as p50/p95/p99.
- **Per-endpoint** — count, errors and p95 per *registered route*. Unknown URLs
  are all folded into one `<unmatched>` bucket, because the path of a request
  nobody registered is chosen by whoever sent it.
- **Events** — the last 50 notable events, each tagged good/warning/serious/
  critical, for the dashboard's event log.

Everything is bounded — `deque(maxlen=…)`, a windowed bucket dict, and a hard
cap on tracked endpoints — so memory does not grow with uptime or with traffic
from someone probing random URLs.

## Dashboard

`wwps/dashboard.py` serves three routes, and only when **both**
`DashboardEnabled` is true and `DashboardToken` is set. Without a token nothing
is registered at all, and startup says so.

| Route | Returns |
| --- | --- |
| `/dashboard` | The HTML page (self-contained, no external assets) |
| `/dashboard/data` | The metrics snapshot as JSON, polled every 2s |
| `/dashboard/metrics` | Prometheus text exposition, for scraping |

`/dashboard` itself is an empty shell — every figure on it comes from
`/dashboard/data`, and that is what the token guards. Enter the token in the
field in the page header; the browser sends it as `X-Dashboard-Token`. Tokens
are never accepted in the query string, so they cannot leak through access logs
or `Referer`, and they are compared in constant time. The responses carry a
content security policy, and everything rendered from request data is escaped —
paths and event messages are attacker-controlled.

The dashboard's own requests are excluded from the metrics they display.

### Design

The dashboard follows a flat-color data-visualization discipline rather than
game-style decoration:

- **No emoji, no gradients.** Status is carried by a small flat dot plus a text
  label, never by color alone — good is green, warning amber, serious orange,
  critical red, from a fixed reserved status palette.
- **One hero figure** (requests per minute), a KPI row of stat tiles, then two
  line charts (request rate; latency p50/p95) and three tables (endpoints,
  counters, events).
- **Charts are honest.** One value axis, a recessive grid, 2px lines,
  direct-labeled end values in the series color, and a two-entry legend on the
  latency chart. Each chart has a Table toggle so the numbers are readable
  without reading pixels.
- **Theme-aware.** Dark by default, light under `prefers-color-scheme: light`.
  The two series colors (blue, amber) were validated for colorblind separation
  and contrast against both surfaces.
- **Tabular figures** in every column of numbers so they align.

The palette and marks follow the data-viz method: categorical hues assigned in
fixed order, status colors reserved and never reused as series, text in ink
tokens rather than the series color.

## Administration

`/admin/*` is served only when `AdminToken` is set, and every call must carry it
in the `X-Admin-Token` header. The dashboard's administration panel is the
intended front end for it.

| Route | Does |
| --- | --- |
| `GET /admin/stats` | Account, device and ban counts |
| `GET /admin/players?q=&limit=` | Search by friend code, user id or player name |
| `GET /admin/player/{gdkey}` | One player's currencies, counts and ban state |
| `POST /admin/grant` | Adjust `ymoney` and `hitodama` by a signed delta |
| `POST /admin/ban` | Ban a save, with a reason shown to the player |
| `POST /admin/unban` | Lift a ban |

Bans are held in memory and in the `ban` table, checked on every request through
`enforce_ownership`, so a ban takes effect on the banned player's next call.

Every grant, ban and unban is written to the `admin_audit` table with the action,
the save, the detail and the caller's address. Read it with:

```sql
select created_at, action, gdkey, detail, actor
from admin_audit order by created_at desc limit 50;
```

## Health probes

`/healthz` answers as long as the process is serving and never touches the
database. `/readyz` returns 200 only when the database answers and the game
tables loaded, 503 otherwise, with a per-check breakdown in the body. Neither is
rate limited or counted in the metrics.

## Tests

`tests/` is a pytest suite covering the parts that are cheap to test in
isolation and expensive to get wrong:

| File | Covers |
| --- | --- |
| `test_crypto_and_tables.py` | Cipher round-trip against the client implementation; the pipe/asterisk table format |
| `test_game_logic.py` | Exp/money curves at known anchors, soul levels, star conditions, mission sorting, item math |
| `test_security.py` | Ownership, battle time/score caps, befriend validation |
| `test_endpoints.py` | Real routing through decryption and encryption with an in-memory store; health probes |
| `test_admin_and_bans.py` | Admin authentication, input validation, bans |
| `test_dashboard.py` | Escaping of attacker-controlled fields, token handling, closed-by-default |
| `test_ratelimit.py` | Token bucket budgets, tiers and refill |

Run them with:

```bash
make install
make test
```

The `store` fixture swaps `user_data`'s database accessors for an in-memory dict,
so no PostgreSQL is needed. `game_config` loads a throwaway `appsettings.json`
and a minimal set of master tables. The column-order test guards the one silent
failure mode of the table format: reordering a row class in `rows.py` corrupts
saves, and that test turns it into a loud failure.
