# Porting notes

WWPS is a behavioural port of the C# puniemu server, not a rewrite. Where the
original did something odd, WWPS does the same odd thing, because the shipped
game client was built against that behaviour. This page lists those cases so they
are not "fixed" by accident, plus the places where the port necessarily differs.

## Quirks reproduced on purpose

**`login.nhn` omits half its response.** `CommonResponse.ToDictionary()`
reflected over `GetFields()`, so C# properties were dropped. The login response
therefore has no `resultCode`, `resultType`, `nextScreenType`, `shopSaleList`,
`hitodamaShopSaleList` or `mstVersionVer`, and none of the login-specific values
that `ConstructAsync` computed (`noticePageList`, `openingTutorialFlg`,
`monthlyPurchasableLeft`, `teamEventButtonHiddenFlg`, `responseCodeTeamEvent`,
`requireAgeConfirm`). `dto.common_response_dict()` reproduces exactly that key
set.

**`userInfoRefresh.nhn` returns PascalCase keys.** Its `ToDictionary()` built the
dictionary with `nameof(...)`, so the keys are the C# member names — `ResultCode`,
`UserData`, `ServerDate`, `YMoneyShopSaleList` — not the JSON names used
everywhere else. Requested extra tables are added under their normal names.

**Collect menu indexes the effect table with the reward table's indexes.** In
`initCollectMenu` / `updateCollectMenu` the loop that fills the effect rows
iterates the *reward* index list. That is a bug in the original, and the rows it
produces are what the client has always received.

**`gameStart` looks up the soultimate level by enemy id.** The "is this Yo-kai's
soultimate maxed" check passes `enemyId` where the Yo-kai id would be expected,
so it almost always misses and the befriend table is generated anyway.

**`gameEnd` adds 10000 to the score.** Only for `gameEnd`, not `gameRetire`.

**Score attack overwrites history before comparing.** `gameEndScoreAttack`
rewrites the all-time best row with a fixed date and the value `2258` before
comparing the new score against it, so the stored best is effectively reset each
run.

**Placeholder player data in the goku and crystal menus.** `initCrystal`,
`updateGokuMenu` and `updateCrystalMenu` start from a hardcoded `ywp_user_data`
(player "superog", 3285 Y-Money) and only replace it if the device lookup
succeeds. `mstVersionMaster` is hardcoded to 16774 in those three responses.

**Hardcoded score-attack content.** The three enemy waves and the two continue
tiers in `gameStartScoreAttack` are literals.

**The login stamp uses two different day lengths.** The "card finished" check
compares against `+8400` seconds while the "advance a day" check uses `+86400`.
The first looks like a missing digit; it is preserved.

**Wibble Wobble gacha duplicates the prize.** The single prize's fields are
hoisted into the response root, `gachaPrizeList` is removed, and the nested
`youkai`, `item` and `convertItemInfo` objects are copied to top level as well.
The client reads them from both places.

**Exp healing before level-up.** `give_youkai_exp` raises a Yo-kai's exp to its
level's base before adding, because Yo-kai granted at a level (login rewards,
evolutions) otherwise sit below every bracket and jump to max level. Evolution
does the same fix-up explicitly after copying the level across.

**`serialConfirm.nhn` is not serial codes.** It is the email-code gateway for
account linking and restore. Real serial-code redemption is unimplemented.

## Deliberate differences

**Path rewriting is inverted.** The C# server rewrote `*.nhn` to `*.nhn/` because
ASP.NET Core treated the bare path as a static file. aiohttp does not, so
`rewrite_middleware` strips the trailing slash instead. Both spellings work.

**Game data is read from disk, not embedded.** C# embedded `Resources\*.txt` into
the assembly. WWPS reads the same files from `Resources/` at startup, keyed by
file name without the extension. This is why the directory must be populated
before the server is useful.

**Threading model.** C# used `ConcurrentDictionary`, `SemaphoreSlim` and
`Parallel.ForEachAsync`. WWPS is single-threaded asyncio: plain dicts,
`asyncio.Lock` per gdkey/udkey, `asyncio.gather` for the flush. The locking
discipline is the same, including taking the two device locks in sorted order in
`transfer_gdkeys`.

**Database driver.** Npgsql becomes asyncpg, so parameters are `$1`-style and the
JSONB column is serialized with `json.dumps` explicitly.

**Email.** `System.Net.Mail.SmtpClient` becomes `smtplib` on a thread executor,
so sending a code does not block the event loop.

**Typed tables.** C# mapped rows onto classes by reflecting over property order.
Python has no equivalent guarantee across construction styles, so `rows.py`
declares the order explicitly as a `FIELDS` list. The order is copied from the C#
declarations and must not be changed.

**Enums.** C# enums become integer constants grouped in classes
(`managers.RewardType`, `managers.MissionType`, …). Values are unchanged, so
stored saves and wire payloads stay compatible.

**Dead code dropped.** The C# `GachaService` soul-level helpers, the
`NonRecursiveConverter` JSON base class and a no-op middleware were not ported;
nothing referenced them.

## Verifying a change

The cipher can be checked against the client-side implementation in
`Tools/sharedLogic/NHN.py`: encrypt a request with `encrypt_req` and confirm
`nhn_crypt.decrypt_request` returns the original, then confirm `decrypt_res`
reads the output of `nhn_crypt.encrypt_response`.

For handlers, the cheapest end-to-end check is to point `user_data.get_ywp_user`
and `set_ywp_user` at an in-memory dict, populate `game_data.gamedata_cache` with
the few tables the endpoint touches, and drive the app with
`aiohttp.test_utils.TestClient`. That runs the real routing, decryption and
encryption path without PostgreSQL or the full game data set.
