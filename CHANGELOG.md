# Changelog

All notable changes to this project are recorded here. Dates are ISO 8601.

## [1.0.0] - 2026-07-26

First packaged release. It carries a security review of the whole server and
the deployment layer that was missing.

### Security

- **Account management codes could not expire.** `serialConfirm` read the expiry
  from the pending-code cache and never compared it, and the cleanup function
  was never called, so a code issued once stayed valid forever. Codes are now
  checked at redemption, swept on every issue, drawn from `secrets` instead of
  the seeded `random`, limited in number, and locked out after five wrong
  attempts per device. Addresses given to `/auth/link` and `/auth/restore` are
  validated, which also closes header injection into the outgoing mail.
- **Stored cross-site scripting in the status dashboard.** The event log and the
  endpoint table were written into the page with `innerHTML` without escaping,
  and both carry the request path, so a crafted URL ran script in the operator's
  browser — the same page where the admin token is typed. Both are escaped now
  and the dashboard sends a content security policy.
- **The dashboard was public when no token was configured.** It failed open, and
  the shipped example configuration had an empty token. The dashboard and the
  admin API are now only served when their tokens are set.
- **Tokens moved out of query strings.** `?token=` is gone; the dashboard and
  admin endpoints read `X-Dashboard-Token` and `X-Admin-Token` and compare them
  in constant time, so tokens no longer reach access logs or `Referer` headers.
- **Unauthenticated account and device creation.** `create_gdkey` inserted a row
  per request with no limit, which grew the database for free and could fill the
  account cache until real players were refused. It now requires a known device,
  enforces `MaxGdkeysPerDevice`, and validates the key format.
- **Currency could be duplicated by concurrent requests.** Handlers read a save,
  await, then write it back, so two parallel purchases both saw the pre-request
  balance. Requests naming the same save are now serialized.
- **Unbounded metric cardinality.** Per-path counters were keyed by the raw URL
  while an unknown URL still reached a handler, so walking random paths grew
  memory without limit. Metrics are keyed by matched route with everything else
  folded into one bucket, and Prometheus label values are escaped.
- **Forwarded headers are no longer trusted by default.** `X-Forwarded-Host`
  decided the asset and API URLs handed to clients. Set `PublicUrl`, or turn on
  the new `TrustProxyHeaders` when a proxy you control is in front.
- Reflected script injection in `/help/inquiry/top.nhn` fixed; friend requests
  can no longer grow another player's save without limit; the ownership cache,
  the lock tables and the account cache are all bounded now; player names are
  stripped of the `|` and `*` characters that delimit the save tables; gacha,
  drop and befriend rolls use the system entropy source; gdkeys, device ids and
  addresses are masked in logs; malformed request bodies answer 400 instead of
  500.

### Added

- Rate limiting (`wwps/ratelimit.py`), strict on authentication, account
  creation and admin endpoints, looser on gameplay. Tunable, and switchable off
  for a LAN server.
- `GET /healthz` and `GET /readyz` for container and orchestrator probes.
- An `admin_audit` table recording every grant, ban and unban.
- Docker image, `docker-compose.yml` with PostgreSQL, and an entrypoint that
  waits for the database and applies the schema and migrations.
- Environment variable configuration: every setting can be given as `WWPS_*`,
  which wins over `appsettings.json`, and the file is optional when the
  environment supplies what is needed. Startup fails with a readable message
  when the configuration cannot work.
- GitHub Actions for lint, tests on 3.11-3.13, dependency audit and an image
  build that boots the container against a real database; a release workflow
  publishing to GHCR on tag.
- `Makefile`, `pyproject.toml` with ruff and pytest configuration,
  `scripts/setup.sh`, pre-commit hooks, `LICENSE`, `SECURITY.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and pull request templates.
- `docs/deployment.md`, covering compose, a TLS reverse proxy, backups and
  upgrades.

### Changed

- `MaxScorePerSecond` now defaults to 20000 rather than 1000000, and the flat
  grace dropped from one million to one hundred thousand. The old defaults
  accepted essentially any score a client claimed.
- Cosmetic profile fields other than the icon are checked against the save's own
  unlock tables before being equipped.
- The account cache evicts idle saves before refusing a new player.
- `Database/schema.sql` is idempotent and adds indexes for the device lookup and
  the admin player list. `Database/migrations/001_admin_audit_and_indexes.sql`
  upgrades an existing install.

### Upgrading from a pre-1.0 checkout

1. Apply `Database/migrations/001_admin_audit_and_indexes.sql`.
2. Set `DashboardToken` and `AdminToken`. Without them the dashboard and the
   admin API are no longer served.
3. Anything that scraped `/dashboard/data?token=...` must send the token as the
   `X-Dashboard-Token` header instead.
4. Behind a proxy, set `PublicUrl` (preferred) or `TrustProxyHeaders: true`.
   Otherwise clients are handed the address they connected to directly.
5. Review `MaxScorePerSecond` against what your players actually score.
