# Game logic

Everything shared between more than one endpoint lives in `wwps/managers.py`.

## Master stage data

`MasterStageData` lazily parses `ywp_mst_stage` and `ywp_mst_stage_condition`
into a normalized form, hiding the fact that Puni Puni ships them as pipe tables
under `tableData` and Wibble Wobble as JSON arrays under `data`. Only the fields
the server needs are kept: stage id, type, boss flag, action cost, and the three
star-condition ids.

Two lookups drive stage unlocking:

- `get_next_stage(stage_id)` — scans forward inside the same map (`stage_id`
  is `mapId * 1000 + n`) for the next stage of type 1, returning `-1` at the end
  of the map.
- `get_unlocked_secret_stage(stage_id, skip)` — finds the secret stage (type 2)
  that a given cleared challenge unlocks. Earlier stages in the map that also
  have challenges consume secret-stage slots, so the function counts those
  first; `skip` distinguishes multiple challenges on the same stage.

## Star and challenge conditions

Condition ids are derived, not stored: condition `n` of a stage is
`stage_id * 10 + n`. Conditions 1–3 are the three stars; 4 and up are the
challenges that unlock secret stages. `compute_stage_condition` evaluates one
condition against a `gameEnd` request.

Implemented condition types include minimum score, minimum combo, minimum link
size, minimum erase size, maximum clear time, maximum puni erased, minimum bonus
balls, minimum fever entries, clear count, "finished with a soultimate"
(optionally by a specific Yo-kai), "used a specific Yo-kai", and maximum enemy
attacks received. Types the original never worked out (clear rank, HP rate,
tribe-specific damage, female-only clears) return `False`.

## Experience and rewards

`score_to_money` and `score_to_exp` are piecewise cubic (PCHIP) fits over
fourteen score brackets, sampled from the real game. Out-of-range scores fall
back to 1000 money / 10000 exp.

`give_youkai_exp` applies exp to one Yo-kai:

1. If the Yo-kai's stored exp is below the base exp of its current level, it is
   raised to that base first. Without this, a Yo-kai that was granted at a level
   (login reward, freshly evolved) has exp below every bracket from its level up,
   the level-up loop never matches, and it jumps straight to max level.
2. Exp is added, then the level table is walked to find the bracket containing
   the new total; that sets level, exp bar denominator, numerator and percentage.
3. The level-open table is checked: if the new level crosses a paid unlock gate,
   the Yo-kai is capped at the gate level and `IsLockedLevel` is set. The gate is
   cleared with `levelLockOff.nhn` for Y-Money.
4. HP and attack scale linearly between the master base and max values over the
   Yo-kai's max level.
5. Progress is reported to the mission system.

## Soultimates

Soul levels 1–7 cost `[0, 1000, 2000, 4000, 6000, 9000, 12000]` points
cumulatively, so the level thresholds are 1000, 3000, 7000, 13000, 22000, 34000.
`add_exp_to_skill` returns before/after exp bars; level 7 is the cap and reports
`isMaxLevel`.

Adding a Yo-kai the player already owns grants 1000 soul points instead — that is
the duplicate mechanic.

## Befriending

`generate_lot_youkai` precomputes the befriend outcome for every combination of
soultimate usage, because the client decides which combination applied only after
the battle. The server sends a list of `(lotPattern, lotResult)` pairs; the
client looks up the pattern matching what the player actually did.

- A pattern is one digit per deck slot, `0`–`3`, counting soultimate uses by that
  slot's befriender. Only slots holding a befriender vary, so the list has
  `4^befrienderCount` entries.
- A result is five bits, one per food tier: no food, 1-heart, 2-heart, 3-heart,
  4-heart. Bit *i* is the roll for "player fed tier *i*".

Rates:

```
base by rank   E 0.11  D 0.10  C 0.08  B 0.06  A 0.01  S 0.01  SS 0.03
food multiplier   none 1.00  1-heart 1.50  2-heart 1.75  3-heart 2.00  4-heart 4.25
super shrine      2.00, and does not stack with food (the higher one wins)
soultimate boost  product over slots of (1 + points * weight / 100),
                  weights 0.6 / 0.3 / 0.1 for the 1st, 2nd and 3rd use
```

Befriender strength comes from `ywp_mst_youkai_skill_level`: either the
`friendlyUpProb` entry of the stats dictionary or the raw soul points, divided by
187.5. The final probability is clamped to `[0, 1]`. `autobefriend` (a scripted
story catch) returns `11111` unconditionally.

## Rare encounters

`rare_enemy_get_drop` reads `rare_enemy` from game data. Entries are either
stage-scoped (a list of stage ids) or map-scoped (a list of map ids with optional
stage exceptions). Stage-scoped entries are rolled first. Rates are integer
percentages compared against `randrange(100)`. Bosses never roll rares.

In `gameStart`, a rolled rare replaces the weakest of the three enemies and
inherits the average HP and attack of the stage.

## Missions

Mission definitions come from two sources: `ywp_mst_mission` (the game's own
table, holding name, type and reward) and `mission_cfg` (a WWPS-specific file
describing series and the numeric parameters, which the real server never exposed
to the client).

`mission_update_progress(gdkey, type, value, ...)` walks the player's visible,
unclaimed missions and updates any whose type matches:

- **cumulative** types add to the counter (total score, stars, cranks, logins,
  items used, Yo-kai added, fusions, purchases, puni popped, bonus balls, fevers,
  soultimates, score-attack score);
- **parameter** types complete when the value equals the configured parameter
  (befriend a specific Yo-kai, buy a specific item, use a specific item);
- **level** and **timed-stage** types compare two values.

Reaching the target sets `CompletePendingReward`; the player then claims it with
`missionReward.nhn`, which grants the reward, marks it `CompleteRewardAcquired`,
and calls `try_unlock_next_mission` to insert the next mission of the series.
Carry-over of progress is suppressed for the parameter-based types.

`sort_user_mission` orders the list as pending reward, then in progress, then
claimed (by id), and optionally clears "new" popups.

## Gacha

`wwps/handlers/gacha.py` rolls against `gacha_pool`, a WWPS-specific file mapping
a gacha id to weighted pools. A pool key starting with `i` is an item pool;
otherwise the key is a rarity number and the pool is a Yo-kai list. `rateUp` gives
per-Yo-kai weights inside a bucket (default 1.0 each).

Two modes handle an already-maxed Yo-kai:

- **convert to item** (Puni Puni) — the maxed Yo-kai becomes its rarity's convert
  item.
- **reroll until valid** (Wibble Wobble) — try the other non-maxed Yo-kai in the
  same bucket; if the whole bucket is maxed, exclude that pool and reroll the
  pool selection, so a maxed-out rarity can land on a different reward type.
  Only if every pool is exhausted does it fall back to a convert item.

Payment is either Y-Money or items. Item payment with action id 81 (Y-Points) is
spent across every Y-Point denomination the player holds until the price is met.

On Wibble Wobble the response carries one prize whose fields are hoisted into the
response root — `gachaPrizeList` is removed and the `youkai`, `item` and
`convertItemInfo` objects are duplicated at top level, because the client reads
them from both places and crashes otherwise.

## Shrine

One visit per UTC day, tracked in `lastAdditionDate`. A visit has a 10% chance of
the super bonus, which sets `ywp_user_addition` and doubles befriend rates for
the next battle; the normal bonus does nothing mechanically. `login.nhn` clears
the flag when a new day starts.

## Fusion

`conflate.nhn` reads `ywp_mst_conflate` for the recipe: two ingredients (each a
Yo-kai or an item), a Y-Money cost and a result Yo-kai. Ingredients are verified
before anything is consumed; Yo-kai ingredients are deleted (and marked as seen
in the medallium), item ingredients are decremented.

## Evolution

`evolveYoukai.nhn` requires the Yo-kai to have reached its master evolution
level. The old Yo-kai and its soultimate are deleted, the evolved form is added,
and the old level is carried across. Because adding a Yo-kai creates it at level
1, the handler then rewrites exp to the base exp of that level and recomputes HP
and attack; otherwise the next exp gain would see exp far below the level's
bracket and run the Yo-kai to max. Deck slots holding the old Yo-kai are
repointed at the evolved one.

## Legends

`releaseYoukai.nhn` checks `ywp_mst_youkai_legend_release`: the player must own
all six seal Yo-kai and must not already have released that legend
(`ywp_user_youkai_legend_release_history`). The legend is then granted and
recorded.
