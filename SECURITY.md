# Security policy

## Reporting a vulnerability

Report privately through
[GitHub security advisories](https://github.com/WibWobPS/wwps/security/advisories/new).
Please do not open a public issue for anything that lets a player read or modify
another player's save, take over an account, or take the server down.

Include the endpoint, a request that reproduces it, and what an attacker gains.
You can expect an acknowledgement within a week.

## What this server does and does not protect

The NHN request/response cipher is **obfuscation, not authentication**. The key
is a constant compiled into the game client, so anyone with the client can read
and forge any request. Nothing in the payload proves who sent it.

What that means for an operator:

- **Terminate TLS in front of this server.** Without HTTPS every save key on the
  wire is readable by anyone on the path. See `docs/deployment.md`.
- A gdkey is a bearer credential. Anyone holding one can act as that save, up to
  what the device-ownership check allows. Keep `EnforceAccountOwnership` on.
- The client reports its own battle results. `ValidateBefriend` and
  `MaxScorePerSecond` bound what it can claim, but a determined client can still
  play within those bounds faster than a human. Tune the limits for your server.
- The dashboard and the admin API are operator tools. They are only served when
  their tokens are set, and their tokens are sent in headers rather than URLs so
  they do not end up in access logs. Do not expose them to the public internet
  without a proxy that adds its own authentication.

## Supported versions

Fixes land on the default branch. There are no maintained release branches.
