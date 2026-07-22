# Endpoints

Unless stated otherwise every route is `POST`, takes an NHN-encrypted JSON body
and returns an NHN-encrypted JSON body.

Two spellings of the account key appear in requests, and they are not
interchangeable per endpoint — the client sends `level5UserId` to some and
`level5UserID` to others. The handlers read whichever the original C# request
class declared.

## Level-5 ID (`GET`, plain JSON)

| Route | Purpose |
| --- | --- |
| `/l5id/api/v1/active` | Puni Puni. Returns the device's udkey and its gdkeys. Creates a device if the client sends none. |
| `/api/v1/active.nhn` | Wibble Wobble. Same, but the udkey arrives in the `TICKET` parameter — the patched client does not send `udkey`. Creates the device if unknown. |
| `/l5id/api/v1/create_gdkey`, `/api/v1/create_gdkey.nhn` | Creates a save and attaches it to the device. Missing `udkey` returns error 4009. |

## Bootstrap and account

| Route | Behaviour |
| --- | --- |
| `init.nhn` | Version gate. Rejects any `appVer` other than `GameVersion` with a dialog. On success returns the asset server URL, the L5ID path and assorted feature flags. |
| `getMaster.nhn` | Serves master tables by name. `tableNames: "all"` expands to the full list in `consts.ALL_TABLE`. Parsed tables are memoized. |
| `createUser.nhn` | Builds a new save: default `ywp_user_data`, the five starter Yo-kai (2157000, 2213000, 2231000, 2235000, 2281000), self-rank rows, empty tables, and every `*_def` default from game data. |
| `login.nhn` | Clears yesterday's shrine flag, resets the daily shop stock, adds the maps listed in `maps_to_add_login`, then returns every table in `LOGIN_TABLES_PUNI`. Also stamps the login time. |
| `getGdkeyAccounts.nhn` | The account-select screen. Any gdkey whose save cannot be read is detached from the device. |
| `deleteUser.nhn` | Requires the friend code as confirmation; deletes only when `finalAnswerFlg` is 1. |
| `userInfoRefresh.nhn` | Returns `ywp_user_data` plus any tables named in `requireInfoList`. |
| `rename.nhn`, `updateProfile.nhn` | Change name / icon / title / plate / effect / codename, then propagate the change into every friend's copy of the player's entry. `updateProfile` rejects an icon the player has not unlocked. |
| `updateTutorialFlg.nhn` | Sets one tutorial flag. |
| `getL5idStatus.nhn` | Static stub; linking to a real Level-5 account is not supported. |
| `serialConfirm.nhn` | Repurposed as the auth gateway (see below), not serial codes. |
| `/auth/link`, `/auth/restore` (`POST`, query params) | Start email linking or restore. Emails a six-digit code, valid 15 minutes. |
| `/help/inquiry/top.nhn` (`GET`) | Serves `dataDownload/help.html` with `window.__PARAMS__` injected — the in-game webview that drives the auth flow. |

### Account linking flow

1. The webview calls `/auth/link?userId=…&email=…`. The server resolves the save,
   generates a code, emails it and caches it against the device's udkey.
2. The player types the code into the game's "confirm action" menu, which posts
   `serialConfirm.nhn`.
3. Link: the email is bound to the udkey. Restore: the gdkeys are transferred
   from the email's previously bound device to this one, in a transaction, and
   the binding is updated.

Codes are single-use and rejected if the requesting device is not the one that
started the flow.

## Menus

| Route | Behaviour |
| --- | --- |
| `initGacha.nhn` | Puni serves the gacha and item master tables plus stamp data; Wibble Wobble serves the gacha table and the player's crank state. Dispatch is on `IsWibWob`. |
| `initGoku.nhn` | Goku menu masters, plus the player's story and intro-release state (missing intro-release rows are created). |
| `updateGokuStory.nhn`, `updateGokuMenu.nhn` | Record a viewed story / unlocked menu. |
| `initCrystal.nhn`, `updateCrystalMenu.nhn` | Crystal menu. The master list is hardcoded (eight entries) — the real table was never dumped. |
| `initCollectMenu.nhn`, `updateCollectMenu.nhn` | Medallium collection sets: filters the master tables to one collect id and creates the player's progress rows. Both routes run the same body. |
| `initScoreAttack.nhn` | Score-attack tables plus a computed week sequence and league (derived from total stars and score). |
| `initBilling.nhn`, `ageConfirm.nhn` | Always answer with the "no paid content" dialog. |
| `getLimitHitodama.nhn` | Empty object. Unused Wibble Wobble endpoint. |
| `getPresentBox.nhn` | Present box tables. |
| `getRanking.nhn` | Ranking tables; which ones depends on `rankType` (3 star, 4 league, 5 medallium, 8 global, otherwise all). |
| `userStageRanking.nhn` | Per-stage ranking; creates an empty entry for a stage that has none. |
| `initWatch.nhn`, `updateWatchReadFlg.nhn` | Watch list and its "seen" flag. |
| `getMission.nhn` | Mission masters plus the player's sorted mission list. |

## World and economy

| Route | Behaviour |
| --- | --- |
| `map.nhn` | Map masters plus the player's map table. |
| `mapWarp.nhn` | Travel to a map. Refuses maps listed in `unavailable_maps`, applies any tutorials from `map_add_tutorial`, creates the map's first stage (locked if the map has unlock requirements) and sets it as the current stage. |
| `mapUnLock.nhn` | Pays a map's unlock cost — Y-Money or "own Yo-kai X at level Y". Friend-point unlocks are not implemented. |
| `buyItem.nhn` | Shop purchase. Validates quantity (1–99), unlock condition, price and the daily stock limit, which resets at UTC midnight. |
| `buyHitodama.nhn` | Buys spirits with Y-Money; returns before/after counts. |
| `useItem.nhn` | Exp orbs (grant exp), soultimate boosters (grant soul points, rejected at level 7), bonus-effect boosters (level up, capped at 5). |
| `loginStamp.nhn` | Daily stamp card. Picks a random card when none is active or the current one finished, advances the day, and grants that day's reward (item, Yo-kai, Y-Money, spirits or icon). |
| `missionReward.nhn` | Claims a completed mission and unlocks the next one in its series. |
| `conflate.nhn` | Fusion. |

## Battle

| Route | Behaviour |
| --- | --- |
| `gameStart.nhn` | Charges a spirit (or a stage pass item), builds the enemy list from `stage_data` plus a possible rare encounter, computes befriend tables, applies tribe unity bonuses to the deck (10/20/25/30% for 2/3/4/5 of a tribe), applies pre-battle tutorial flags and issues the session `requestId`. |
| `gameEnd.nhn` | Validates the session, awards money and exp, evaluates star and challenge conditions, unlocks the next stage / secret stages / next maps, records the medallium, grants a befriended Yo-kai and first-clear rewards, and reports progress to six mission types. |
| `gameRetire.nhn` | The same handler with stage progression skipped. |
| `gameContinue.nhn` | Charges 500 Y-Money to continue. |
| `gameUseItem.nhn` | Consumes one battle item. |
| `gameStartScoreAttack.nhn`, `gameEndScoreAttack.nhn` | Score attack. The enemy waves and continue costs are hardcoded; the end handler tracks weekly and all-time best scores and grants exp scaled by damage dealt. |
| `executeGacha.nhn`, `gacha.nhn` | Crank. Both names route to the same handler. |

`gameEnd` adds 10000 to the reported score before doing anything else. The retail
game does this too.

## Friends

| Route | Behaviour |
| --- | --- |
| `friend.nhn` | Friend list, incoming requests and rank lists, with relative timestamps rendered. |
| `friendSearch.nhn` | Look a player up by friend code. |
| `friendRequest.nhn` | Send a request. Response code 1 means the sender's list is full, 2 means the target's is. |
| `friendRequestAccept.nhn` | Adds each player to the other's friend list and seeds the three rank lists on both sides. |
| `friendRequestDelete.nhn` | Decline a request. |
| `friendDelete.nhn` | Remove a friend from every list on both sides. |

## Fallback

Any unrouted path returns a dialog reading `Unimplemented request:` followed by
the path, titled with `ServerName`. This makes missing endpoints visible in-game
instead of failing silently.
