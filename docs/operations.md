# Operations: security, logging, metrics, dashboard

This covers the operational layer added on top of the game server: the anti-abuse
checks, the logger, the metrics registry and the status dashboard.

## Security

Two classes of abuse are checked. Both are on by default and each has a config
flag (`EnforceAccountOwnership`, `ValidateBefriend`).

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

### Befriend validation

`gameStart` computes and stores the befriend odds table in `last_enemy`. At
`gameEnd`, a claimed catch (`dropYoukaiFlg == 1`) is checked against that stored
table: the server reconstructs the lot pattern from the soultimate uses the
client reported, finds the matching entry, and confirms the result bit for the
food tier the player used is set. A catch that was never rolled is dropped from
the response and counted as `cheat_befriend`.

This closes the largest economy exploit: without it, sending `dropYoukaiFlg: 1`
for any on-stage enemy grants that Yo-kai unconditionally.

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
- **Per-endpoint** — count, errors and p95 per path.
- **Events** — the last 50 notable events, each tagged good/warning/serious/
  critical, for the dashboard's event log.

Everything is bounded (`deque(maxlen=…)` and a windowed bucket dict), so memory
does not grow with uptime.

## Dashboard

`wwps/dashboard.py` serves three routes when `DashboardEnabled` is true:

| Route | Returns |
| --- | --- |
| `/dashboard` | The HTML page (self-contained, no external assets) |
| `/dashboard/data` | The metrics snapshot as JSON, polled every 2s |
| `/dashboard/metrics` | Prometheus text exposition, for scraping |

Set `DashboardToken` to require `?token=…` (or an `X-Dashboard-Token` header) on
all three. The dashboard's own requests are excluded from the metrics they
display.

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

## Tests

`tests/` is a pytest suite covering the parts that are cheap to test in
isolation and expensive to get wrong:

| File | Covers |
| --- | --- |
| `test_crypto_and_tables.py` | Cipher round-trip against the client implementation; the pipe/asterisk table format |
| `test_game_logic.py` | Exp/money curves at known anchors, soul levels, star conditions, mission sorting, item math |
| `test_security.py` | Ownership, battle time/score caps, befriend validation |
| `test_endpoints.py` | Real routing through decryption and encryption with an in-memory store; the dashboard |

Run them with:

```bash
pip install -r requirements-dev.txt
pytest
```

The `store` fixture swaps `user_data`'s database accessors for an in-memory dict,
so no PostgreSQL is needed. `game_config` loads a throwaway `appsettings.json`
and a minimal set of master tables. The column-order test guards the one silent
failure mode of the table format: reordering a row class in `rows.py` corrupts
saves, and that test turns it into a loud failure.
