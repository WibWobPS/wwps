# Wire protocol

Every game-server endpoint speaks the same envelope: an HTTP POST whose body is a
single base64url token. The Level-5 ID endpoints (`/api/v1/active`,
`/api/v1/create_gdkey`) are the exception — they are plain GET requests with
plain JSON responses.

## The NHN cipher

Both directions use AES-128 in ECB mode with PKCS#7 padding and one hardcoded
key, plus a salted double-SHA1 digest. The base64 is URL-safe: `+` and `/` are
transmitted as `-` and `_`.

```
key    a8 65 d7 e5 e2 45 8f 8c e1 b5 ec d0 87 e5 45 94
salt   "0bk2kvtFE2"
```

### Client to server (`decrypt_request`)

```
token -> url-unsafe -> base64 decode -> AES-ECB decrypt -> unpad
      -> skip 20 bytes (the client's SHA1 digest) -> UTF-8 JSON
```

The digest the client prepends is not verified. The original C# server skipped it
too, and there is no shared secret beyond the key itself, so verifying it would
add nothing.

### Server to client (`encrypt_response`)

```
JSON -> UTF-8 -> gzip
     -> digest = SHA1(salt + SHA1(salt + " " + gzipped))
     -> AES-ECB encrypt(pad(digest + gzipped)) -> base64 -> url-safe
```

Note the asymmetry: responses are gzipped before encryption, requests are not.
The digest is computed over the compressed bytes, and the first hash includes a
space between salt and payload while the second does not. Both quirks are part
of the format the client expects.

`Tools/sharedLogic/NHN.py` contains the client-side implementation of the same
scheme and can be used to encode test requests or decode captured responses.

## Response envelopes

Three shapes are used, and the differences are load-bearing because the original
C# serializer produced them by accident.

### `dto.common_response_full()`

The full C# `CommonResponse` serialization: fields and properties, including
nulls.

```json
{
  "serverDt": 1750000000000,
  "resultCode": 0,
  "nextScreenType": 0,
  "resultType": 0,
  "mstVersionMaster": 16774,
  "shopSaleList": null,
  "ymoneyShopSaleList": [5],
  "hitodamaShopSaleList": null,
  "ywpToken": "",
  "token": "",
  "dialogMsg": "",
  "webServerIp": "https:\\/\\/gameserver.yw-p.com",
  "dialogTitle": "",
  "storeUrl": "",
  "mstVersionVer": 0
}
```

Most handlers start here and add their own keys.

### `dto.common_response_dict()`

Used by `login.nhn`. The C# `CommonResponse.ToDictionary()` reflected over
`GetFields()` only, so C# *properties* were silently dropped. That means the
login response has no `resultCode`, `resultType`, `nextScreenType`,
`shopSaleList`, `hitodamaShopSaleList`, `mstVersionVer` — and none of the
login-specific values (`noticePageList`, `openingTutorialFlg`,
`monthlyPurchasableLeft`, …) that `ConstructAsync` computed. WWPS reproduces the
same key set, because the shipped client works against it.

### `consts.msg_box_response(message, title)`

An in-game dialog box. Used for every player-visible error: not enough Y-Money,
wrong app version, invalid session, unimplemented endpoint.

```json
{
  "dialogMsg": "...", "dialogTitle": "...",
  "gameServerUrl": "https:\\/\\/gameserver.yw-p.com",
  "resultCode": 0, "storeUrl": "", "resultType": 2, "nextScreenType": 1
}
```

`resultType: 2` is what makes the client show the dialog instead of proceeding.

## Adding tables to a response

`utils.add_tables_to_response(tables, result, is_download_once, gdkey)` is the
shared helper that fills a response with table payloads. For each requested name:

- `ywp_user*` names are read from the player's data. With `is_download_once=True`
  the whole account is fetched once and then indexed, instead of one lookup per
  table.
- Anything else is read from the static game data cache. If the file parses as
  JSON and the top level object has a `data` or `tableData` key, only that inner
  value is sent — that is the "cud structure" the game data dumps use.
- Unknown names are skipped with a log line rather than failing the request.

## Session tokens

`gameStart` and `gameStartScoreAttack` generate a `requestId` (a millisecond
timestamp), store it in the player's `ywp_user_requestid` table and return it.
`gameEnd`, `gameRetire` and `gameEndScoreAttack` refuse to process a result whose
`requestId` does not match, and clear the stored value on success. This prevents
replaying a battle result.
