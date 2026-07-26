# WibWobPS (WWPS)

[![CI](https://github.com/WibWobPS/wwps/actions/workflows/ci.yml/badge.svg)](https://github.com/WibWobPS/wwps/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A private server for *Yo-kai Watch Puni Puni* / *Wibble Wobble*, written in
Python. It is a behavioural port of the C#
[puniemu](https://github.com/hxgohxrr/puniemu) server: same NHN request/response
cipher, same table formats, same game rules and endpoints, running on aiohttp and
asyncpg instead of ASP.NET Core and Npgsql.

This project is non-profit. In-app purchases are disabled. It is not affiliated
with NHN.

## Quick start with Docker

```bash
cp .env.example .env          # set POSTGRES_PASSWORD and the two tokens
docker compose up -d
curl localhost:8080/healthz
```

That brings up PostgreSQL, applies the schema and migrations, and starts the
server on port 8080.

## Quick start without Docker

```bash
./scripts/setup.sh            # virtualenv, dependencies, appsettings.json, tokens
$EDITOR appsettings.json      # set PostgresConnectionString
DATABASE_URL=postgresql://... make schema
make run
```

Either way you also need to populate `Resources/` with the game's master tables
and the server-side data files. They were embedded in the C# assembly and were
never committed, so they are not part of this repository. See
[docs/configuration.md](docs/configuration.md).

Every setting can also be given as an environment variable (`WWPS_ADMIN_TOKEN`,
`WWPS_PORT`, …), which takes precedence over `appsettings.json`.

## Operating it

| Endpoint | Purpose |
| --- | --- |
| `/healthz` | The process is up. Used by the container healthcheck. |
| `/readyz` | The database answers and the game tables loaded. |
| `/dashboard` | Status dashboard. Served only when `DashboardToken` is set. |
| `/dashboard/metrics` | Prometheus exposition. |
| `/admin/*` | Player search, currency grants, bans. Needs `AdminToken`. |

The dashboard and admin tokens travel in the `X-Dashboard-Token` and
`X-Admin-Token` headers, never in the URL.

**Put TLS in front of this server.** The NHN cipher is obfuscation with a key
that ships inside the game client — it authenticates nothing. See
[SECURITY.md](SECURITY.md) and [docs/deployment.md](docs/deployment.md).

## Development

```bash
make install
make test
make lint
```

The test suite runs without a database or game files. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

| Document | Contents |
| --- | --- |
| [architecture.md](docs/architecture.md) | Module map and the life of a request |
| [protocol.md](docs/protocol.md) | The NHN cipher, response envelopes, session tokens |
| [data-model.md](docs/data-model.md) | Database schema, account cache, the pipe/asterisk table format |
| [game-logic.md](docs/game-logic.md) | Stages, conditions, exp curves, befriend odds, missions, gacha |
| [endpoints.md](docs/endpoints.md) | Every route and what it does |
| [configuration.md](docs/configuration.md) | `appsettings.json`, environment variables, `Resources/` |
| [deployment.md](docs/deployment.md) | Docker, reverse proxy and TLS, backups, upgrades |
| [operations.md](docs/operations.md) | Security checks, rate limits, logging, metrics, dashboard, tests |
| [porting-notes.md](docs/porting-notes.md) | Quirks kept from the C# server, and where the port differs |

## Layout

```
wwps/            server package
  app.py         routes, middlewares, startup
  nhn_crypt.py   request/response cipher
  user_data.py   PostgreSQL + write-back account cache
  managers.py    shared game logic
  security.py    account ownership and anti-cheat checks
  ratelimit.py   per-client token buckets
  validate.py    client input validation
  metrics.py     in-process metrics registry
  dashboard.py   status dashboard (HTML + JSON + Prometheus)
  logging_setup.py  colored structured logging
  handlers/      one module per endpoint family
tests/           pytest suite
Database/        schema.sql and migrations
Resources/       game data (you supply this)
dataDownload/    static files served to the client
docker/          container entrypoint
scripts/         setup helper
Tools/           data-download helper scripts from the C# repo
docs/            documentation
```

## Credits

Original C# server: Zura, DarkCraft, wibwob_yt, with reverse engineering help
from onepiecefreak3 and kuronosuFear, logo by picky_x_keizen.
