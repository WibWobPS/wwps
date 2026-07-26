# Deployment

Configuration keys are described in [configuration.md](configuration.md); the
operational layer in [operations.md](operations.md).

## Docker Compose

```bash
cp .env.example .env
openssl rand -hex 32           # paste into WWPS_DASHBOARD_TOKEN
openssl rand -hex 32           # paste into WWPS_ADMIN_TOKEN
docker compose up -d
docker compose logs -f server
```

The compose file starts PostgreSQL with a healthcheck and only starts the server
once the database answers. `docker/entrypoint.sh` then waits for the DSN to
respond, applies `Database/schema.sql` and every file in
`Database/migrations/`, and execs the server. All of that is idempotent, so a
restart is safe.

Two directories are mounted read-only from the checkout:

- `Resources/` — the game's master tables. Nothing serves a real client without
  them.
- `dataDownload/` — static files the client fetches, including `help.html`.

The image runs as an unprivileged user and declares a healthcheck against
`/healthz`.

To publish only on the loopback interface because a proxy is in front:

```
WWPS_BIND=127.0.0.1:8080
```

## Reverse proxy and TLS

**Do this.** The NHN cipher's key ships inside the game client, so it hides
nothing from anyone who wants to look. Over plain HTTP, every save key on the
wire is readable by anyone on the path.

Two settings matter behind a proxy:

- `PublicUrl` — the address players use. The launching payload hands this to the
  client as its asset and API base. Set it and you are done.
- `TrustProxyHeaders` — only if you cannot set `PublicUrl`. It makes the server
  believe `X-Forwarded-Proto` and `X-Forwarded-Host`, which is safe only when
  your proxy overwrites those headers on every request. Leave it off otherwise:
  a forged header would otherwise redirect clients to someone else's server.

### Caddy

```
wwps.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Caddy obtains a certificate on its own and sets the forwarded headers. Set
`WWPS_PUBLIC_URL=https://wwps.example.com`.

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name wwps.example.com;

    ssl_certificate     /etc/letsencrypt/live/wwps.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wwps.example.com/privkey.pem;

    # The client uploads small encrypted bodies; nothing needs to be large.
    client_max_body_size 1m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host  $host;
    }

    # Operator surfaces. Restrict them even though both need a token.
    location /dashboard { allow 10.0.0.0/8; deny all; proxy_pass http://127.0.0.1:8080; }
    location /admin     { allow 10.0.0.0/8; deny all; proxy_pass http://127.0.0.1:8080; }
}
```

Note `X-Forwarded-For` is *set*, not appended — the client's own header is
discarded, which is what makes the rate limiter's view of the client honest.

## Health probes

| Path | Meaning |
| --- | --- |
| `/healthz` | The process is serving. Never touches the database. |
| `/readyz` | 200 when the database answers and the game tables loaded, 503 otherwise, with a per-check breakdown in the body. |

Use `/healthz` as a liveness probe and `/readyz` as a readiness probe. Neither
is rate limited or recorded in the metrics.

## Backups

Everything durable is in PostgreSQL; saves are held in memory for up to a minute
before being flushed, so a backup taken during play can be a flush interval
behind.

```bash
docker compose exec -T postgres pg_dump -U wwps wwps | gzip > wwps-$(date +%F).sql.gz
```

Restoring:

```bash
gunzip -c wwps-2026-07-26.sql.gz | docker compose exec -T postgres psql -U wwps wwps
```

`Resources/` and `dataDownload/` are static inputs you supply — back them up
wherever you got them from, they are not in the database.

## Upgrading

```bash
git pull
docker compose build
docker compose up -d
```

The entrypoint applies any new migrations on boot. Read `CHANGELOG.md` first
when the major version changes; 1.0.0 in particular stops serving the dashboard
and the admin API unless their tokens are set.

Shutdown flushes every dirty save, with a 30 second budget. `docker compose
down` sends `SIGTERM` and waits, so use it rather than killing the container.

## Running without containers

```bash
./scripts/setup.sh
DATABASE_URL=postgresql://... make schema
make run
```

For a long-lived host install, run it under systemd with the same environment
variables the compose file sets, `Restart=on-failure`, and a dedicated
unprivileged user.
