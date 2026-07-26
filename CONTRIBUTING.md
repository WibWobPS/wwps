# Contributing

## Getting set up

```bash
make install        # virtualenv in .venv with the runtime and dev dependencies
make test
make lint
```

Or with containers, which also brings up PostgreSQL:

```bash
cp .env.example .env      # then edit it
make docker-up
```

The server needs the game's master tables in `Resources/` to serve a real
client. The test suite does not — it substitutes small fixtures, so
`make test` works on a fresh checkout.

## House style

- Match the surrounding code. Four spaces, ~90 columns, standard library first
  in imports, `from __future__ import annotations` at the top of every module.
- Comment why, not what, and only where the reason is not obvious from the code.
- One module per endpoint family under `wwps/handlers/`. Shared game rules go in
  `wwps/managers.py`, shared request helpers in `wwps/utils.py`.
- Read client input through `wwps/validate.py` rather than using `req.get(...)`
  directly wherever the value is used in arithmetic, indexing or a key.
- Never log a whole gdkey, device id or e-mail address. `logging_setup.mask()`
  exists for that.

## Changes that touch the protocol

This server is a behavioural port of the C# *puniemu* server. If a change makes
the server answer differently from the original, say so in the pull request and
record it in `docs/porting-notes.md`. The client is unforgiving about response
shapes, so a change that "looks equivalent" often is not.

## Before opening a pull request

- `make lint` and `make test` are green.
- New behaviour has a test. The suite runs without a database; follow the
  `store` fixture in `tests/conftest.py`.
- Configuration changes are reflected in `appsettings.example.json`,
  `.env.example` and `docs/configuration.md`.
- User-visible or operational changes get a line in `CHANGELOG.md`.

## Security

Do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).
