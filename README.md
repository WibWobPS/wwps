# WibWobPS (WWPS)

A private server for *Yo-kai Watch Puni Puni* / *Wibble Wobble*, written in
Python. It is a behavioural port of the C#
[puniemu](https://github.com/hxgohxrr/puniemu) server: same NHN request/response
cipher, same table formats, same game rules and endpoints, running on aiohttp and
asyncpg instead of ASP.NET Core and Npgsql.

This project is non-profit. In-app purchases are disabled. It is not affiliated
with NHN.

## Quick start

```bash
pip install -r requirements.txt
psql "$DATABASE_URL" -f Database/schema.sql
cp appsettings.example.json appsettings.json   # then edit it
python -m wwps
```

Serves on `0.0.0.0:8080`. A status dashboard is at `/dashboard`.

Run the tests with:

```bash
pip install -r requirements-dev.txt
pytest
```

You also need to populate `Resources/` with the game's master tables and the
server-side data files. They were embedded in the C# assembly and were never
committed, so they are not part of this repository. See
[docs/configuration.md](docs/configuration.md).

## Documentation

| Document | Contents |
| --- | --- |
| [architecture.md](docs/architecture.md) | Module map and the life of a request |
| [protocol.md](docs/protocol.md) | The NHN cipher, response envelopes, session tokens |
| [data-model.md](docs/data-model.md) | Database schema, account cache, the pipe/asterisk table format |
| [game-logic.md](docs/game-logic.md) | Stages, conditions, exp curves, befriend odds, missions, gacha |
| [endpoints.md](docs/endpoints.md) | Every route and what it does |
| [configuration.md](docs/configuration.md) | `appsettings.json`, `Resources/`, deployment |
| [porting-notes.md](docs/porting-notes.md) | Quirks kept from the C# server, and where the port differs |
| [operations.md](docs/operations.md) | Security checks, logging, metrics, the status dashboard, and tests |

## Layout

```
wwps/            server package
  app.py         routes, middlewares, startup
  nhn_crypt.py   request/response cipher
  user_data.py   PostgreSQL + write-back account cache
  managers.py    shared game logic
  security.py    account ownership and anti-cheat checks
  metrics.py     in-process metrics registry
  dashboard.py   status dashboard (HTML + JSON + Prometheus)
  logging_setup.py  colored structured logging
  handlers/      one module per endpoint family
tests/           pytest suite
Database/        schema.sql
Resources/       game data (you supply this)
dataDownload/    static files served to the client
Tools/           data-download helper scripts from the C# repo
docs/            documentation
```

## Credits

Original C# server: Zura, DarkCraft, wibwob_yt, with reverse engineering help
from onepiecefreak3 and kuronosuFear, logo by picky_x_keizen.
