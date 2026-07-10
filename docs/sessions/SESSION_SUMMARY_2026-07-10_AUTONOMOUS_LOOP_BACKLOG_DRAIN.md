# Session Summary — 2026-07-10 — Autonomous /loop backlog drain + live inventory crash fix

## Scope

A 10-iteration autonomous parity-loop run that drained the remaining documented
gap backlog from `SESSION_STATUS.md` and fixed a **live runtime crash** the user
reported mid-session (`inventory` → "Sorry, there was an error processing that
command."). Every fix was verified against ROM 2.4b6 C source (the user
re-emphasised ROM-FAITHFUL twice; a durable directive was added to AGENTS.md).
Picked up from the v2.14.298 command-handler-sweep handoff. Nine documented gaps
closed + one crash fix + one policy commit; version 2.14.298 → **2.14.307**. All
local on `master`, unpushed.

## Outcomes

### `DROP-001` — ✅ FIXED (2.14.299)

- **Python**: `mud/commands/inventory.py:do_drop`, new `mud/math/c_compat.py:rom_is_number`/`rom_atoi`
- **ROM C**: `src/act_obj.c:505-523`, `src/interp.c:696` (`is_number`)
- **Fix**: coin branch gated on `str.isdigit()`; ROM gates on `is_number` (accepts leading `+`/`-`). `drop -5 coins` now enters the coin branch → "Sorry, you can't do that." Closed the `is_number`/`atoi` class with shared helpers.
- **Tests**: `tests/integration/test_drop_command.py::test_drop_negative_coin_amount_enters_coin_branch_like_rom_is_number` (16/16 file green)

### `AURA-001` — ✅ FIXED (2.14.300) — the reported live crash

- **Python**: `mud/utils/act.py:_char_affected`
- **ROM C**: `src/act_info.c` `format_obj_to_char` (`IS_AFFECTED(ch, AFF_DETECT_*)`)
- **Fix**: `inventory`/`equipment` crashed with `ImportError: cannot import name 'skill_lookup' from 'mud.skills.registry'` for any player with a string-typed affect. Latent until INVEN-001/EQUIP-002 wired `format_obj_to_char` into those displays. ROM gates aura tags on a bitfield test of `ch->affected_by`, not an affect-list walk — rewrote `_char_affected` to be that bitfield test and deleted the non-ROM branch. **ROM-faithful, not a papered-over import swap** (per user guidance).
- **Tests**: `tests/test_char_affected_skill_lookup.py` (3 cases incl. real aura render)

### ROM-FAITHFUL directive — ✅ ADDED (docs)

- **File**: `AGENTS.md` "ROM Parity Rules (CRITICAL)" — a strong, non-negotiable directive that every fix (crash fixes and one-liners included) must reproduce ROM behavior, verified by reading the C first; uses AURA-001 as the worked anti-pattern and requires tests to assert the ROM contract, not "no longer throws."

### `WIMPY-002` — ✅ FIXED (2.14.301)

- **Python**: `mud/commands/remaining_rom.py:do_wimpy`
- **ROM C**: `src/act_info.c:2811` (`atoi`)
- **Fix**: `int()` raised on `"12x"` → 0; ROM `atoi("12x")` == 12. Routed through the shared `rom_atoi`. Sibling of DROP-001 (same class, now fully closed).
- **Tests**: `tests/test_player_wimpy.py::...::test_wimpy_numeric_prefix_parses_leading_digits_like_rom_atoi` (8/8 green)

### `STEAL-001` — ✅ FIXED (2.14.302)

- **Python**: `mud/commands/thief_skills.py:do_steal`
- **ROM C**: `src/act_obj.c:2249,2295,2328`
- **Fix**: `do_steal` never called `check_improve`, so the steal skill never improved. Wired the registry's ROM-faithful `check_improve` into the caught (`FALSE,2`), coin (`TRUE,2`), and item (`TRUE,2`) paths.
- **Tests**: `tests/integration/test_steal_command.py::test_steal_calls_check_improve_on_all_rom_paths` (17/17 green)

### `RESCUE-002` — ✅ FIXED (2.14.303)

- **Python**: `mud/skills/handlers.py:rescue`
- **ROM C**: `src/fight.c:3089-3091`
- **Fix**: `rescue` built its three lines from raw `name`, so an NPC rescuer leaked its keyword name. Rewrote through `act_format` (= ROM `act()`/`$n`/`$N` PERS + INV-027 masking + INV-029 first-letter cap), TO_NOTVICT per-observer. Confirmed `skill_handlers.rescue` is a live path (`do_rescue` calls it on success).
- **Tests**: `tests/integration/test_rescue_single_delivery.py::test_rescue_renders_npc_party_via_pers_short_descr`

### `TRIP-002` — ✅ FIXED (2.14.304) — (+ TRIP size-modifier suspicion resolved)

- **Python**: `mud/commands/combat.py:do_trip`
- **ROM C**: `src/fight.c:2749` (failure), `:2906-2909` (size)
- **Fix**: `do_trip` is void; the failure branch's `apply_damage(show=True)` pushed the miss line AND returned it → double-delivery (count == 2, reproduced). Now returns `""`. Rewrote the 3 `TestTripRomParity` chance tests (which asserted a truthy failure return) to measure the boundary and lock the size/dex/level coefficients. **Resolved the "size shift ~7 not 20" suspicion as a measurement artifact** — `check_improve` was bumping `skills["trip"]` across the sweep; with it disabled the boundary is a clean 44→34→24 (exactly 10 per size step, ROM-correct).
- **Tests**: `tests/integration/test_trip002_single_delivery.py` + `TestTripRomParity` (20/20 green)

### `PUT-006` — ✅ FIXED (2.14.305)

- **Python**: `mud/commands/obj_manipulation.py:do_put`
- **ROM C**: `src/act_obj.c:354-362`
- **Fix**: container defaulted to the last word; ROM uses the second token (`arg2`), re-read to the third only on `in`/`on`. `put ring bag junk` targeted `junk`, now `bag`. Rewrote to the faithful `arg1`/`arg2` parse + empty-arg2 guard.
- **Tests**: `tests/integration/test_put_room_messages.py::test_put_006_container_is_second_token_not_last_word` (19/19 across PUT suites)

### `LOCK-003` — ✅ FIXED (2.14.306)

- **Python**: `mud/commands/doors.py:do_lock`, `do_unlock`
- **ROM C**: `src/act_move.c:669`, `:805`
- **Fix**: door key guard used `key_vnum <= 0` where ROM uses `< 0`; a `key: 0` exit diverged. Both door branches now gate on `< 0`. Corrected a mis-specified test (`test_lock_nolock_door_blocked` → `test_lock_keyless_door_reports_lack_of_key`) — ROM's `do_lock` door branch has **no** EX_NOLOCK check.
- **Tests**: `tests/integration/test_lock003_door_key_threshold.py` (13/13 across door suites)

### `GIVE-006` — ✅ FIXED (2.14.307) — resolved to STRICT PARITY

- **Python**: `mud/commands/give.py:do_give`
- **ROM C**: `src/act_obj.c:783`, `src/handler.c:2306` (`get_obj_carry`)
- **Fix**: giving a worn item emitted the more-helpful-but-non-ROM "You must remove it first."; ROM `get_obj_carry` excludes worn items → "You do not have that item." (the "remove it first" branch is ROM dead code). Per the ROM-FAITHFUL rule, dropped the `_find_equipped_obj` fallback (and its now-dead helper). **Revertible** if a UX exception is later wanted.
- **Tests**: `tests/integration/test_give_command.py::test_give_equipped_item_reports_not_carried_like_rom` (23/23 across give suites)

## Files Modified

- `mud/math/c_compat.py` — new `rom_is_number`/`rom_atoi` helpers (C `is_number`/`atoi`)
- `mud/commands/inventory.py`, `mud/commands/remaining_rom.py` — use the helpers (DROP-001, WIMPY-002)
- `mud/utils/act.py` — `_char_affected` is now ROM `IS_AFFECTED` bitfield test (AURA-001)
- `mud/commands/thief_skills.py` — `check_improve` on all steal paths (STEAL-001)
- `mud/skills/handlers.py` — `rescue` via `act_format` PERS (RESCUE-002)
- `mud/commands/combat.py` — `do_trip` failure returns "" (TRIP-002)
- `mud/commands/obj_manipulation.py` — `do_put` ROM arg1/arg2 parse (PUT-006)
- `mud/commands/doors.py` — door key guard `< 0` (LOCK-003)
- `mud/commands/give.py` — drop worn-item fallback (GIVE-006)
- `tests/...` — 9 new/updated tests (one per gap) + TRIP chance-test rewrite
- `docs/parity/{ACT_OBJ,ACT_INFO,ACT_MOVE,FIGHT}_C_AUDIT.md` — flipped rows: DROP-001, AURA-001, WIMPY-002, STEAL-001, RESCUE-002, TRIP-002, PUT-006, LOCK-003, GIVE-006
- `AGENTS.md` — ROM-FAITHFUL directive
- `CHANGELOG.md` — 9 `Fixed` entries
- `pyproject.toml` — 2.14.298 → 2.14.307

## Test Status

- Full suite: **6186 passed, 4 skipped** (`.venv/bin/python -m pytest`, 278s parallel). Zero failures.
- `ruff check .` clean on all touched files.

## Next Steps

The documented gap backlog is now **drained** — the only deferred item is
**DESC-001** (latent: a plain-replace description ≥1024 chars, unreachable while
`MAX_INPUT_LENGTH == 256`; removing the guard drops a harmless safety cap for zero
parity benefit — left as-is by design). Next sessions should return to the
**cross-file invariants / divergence-class** passes (per AGENTS.md, the active
mode when the per-file tracker has no Partial/Not-Audited rows): pick a candidate
area (affect ticks, position transitions, mob-script triggers, group/follower
chains) and run the probe-then-scope method. **Gating action: review + push the
v2.14.299 → 2.14.307 commits (all local on `master`).**
