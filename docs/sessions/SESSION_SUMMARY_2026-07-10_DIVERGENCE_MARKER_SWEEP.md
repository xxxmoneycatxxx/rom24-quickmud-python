# Session Summary — 2026-07-10 — Divergence-marker sweep (4 fixes) + faithful-probe loop

## Scope

Autonomous 10-iteration parity loop, picking up from the DB-002 + stale-doc
handoff (v2.14.310, per-file audit tracker at 100%, documented backlog drained →
cross-file / divergence-class probe mode). Each iteration was a
probe → **either** close a real gap (failing-test-first, one commit) **or** verify
faithful and record. Yield: **4 real fixes + 1 docs correction + 5
verified-faithful probes** — well above the prior run's ~1-gap-per-7 estimate.

The high-yield heuristic this session: **grep `mud/` for self-admitted
divergence markers** ("not yet ported", "simplified version", "approximation",
"until … gap closes"). Three of the four fixes came straight from that sweep — a
code comment confessing a divergence is a pre-filed gap nobody assigned an ID.

## Outcomes

### `GL-049` — ✅ FIXED (v2.14.311)

- **Python**: `mud/advancement.py:advance_level`, `mud/math/stat_apps.py`
- **ROM C**: `src/update.c:81-95`
- **Gap**: `advance_level` mana/move used a static `LEVEL_BONUS` dict instead of
  ROM's stat-scaled `number_range` rolls. Two divergences: wrong per-level values
  (a high-INT mage / high-CON warrior was mis-paid every level), **and** an RNG
  desync — ROM draws `number_range` 3× per level-up (hp, mana, move) while the
  port drew only 1× (hp), shifting the shared Mitchell-Moore stream by 2 draws
  for every downstream consumer whenever a PC leveled mid-combat tick (the
  GL-026/GL-045/GL-046 hazard class, on the advancement path).
- **Fix**: added `mana_gain_stat_cap`/`move_gain_stat_cap` accessors; rolled
  mana then move after the hp roll (draw order preserved), halving for
  `!gains_mana` (ROM `fMana`) with `c_div(x*9,10)` + `max(2/6,…)` floors.
- **Tests**: `tests/test_advancement.py::test_advance_level_rolls_mana_and_move_like_rom`
  (locks the 3-draw order + values) + `::test_advance_level_non_fmana_class_halves_mana`;
  updated 7 existing advancement assertions (`test_advancement.py` ×2,
  `test_character_advancement.py` ×5) to ROM-rolled values.
- **Collateral**: hardened `test_kill_mob_grants_xp_integration` — its blanket
  `number_bits=lambda:19` pin poisoned the Midgaard mayor's `spec_cast_mage →
  _select_spell` `while True: number_bits(4)` loop (19 is out of range for 4
  bits → infinite hang). A pre-existing landmine, latent by RNG luck, tripped by
  GL-049's stream shift. **Scoped the pin to `width==5`** (the THAC0 roll),
  delegating other widths to the real generator so `_select_spell` terminates.

### `LOOK-018` — ✅ FIXED (v2.14.312)

- **Python**: `mud/world/look.py:_room_occupant_line`
- **ROM C**: `src/act_info.c:304-401` (`show_char_to_char_0`)
- **Gap**: the room occupant list omitted ROM's furniture branch — a char on a
  furniture object (`victim->on != NULL`) should render "is `<verb>` `<at|on|in>`
  `<furniture short_descr>`." for SLEEPING/RESTING/SITTING/STANDING (preposition
  from the furniture's `value[2]` bits). Python ported only the `on==NULL` path
  ("is sitting here."). Runtime already tracks `char.on`; only the display was
  missing.
- **Fix**: `_furniture_position_suffix` + `_FURNITURE_POSITION` verb/bit map;
  else-branch prefers it when `victim.on` is set.
- **Tests**: `tests/integration/test_look_char_tags_show_char_to_char_0.py` (11:
  four positions × at/on/in + on==NULL guard).

### `EFFECTS-006` — ✅ FIXED (v2.14.313)

- **Python**: `mud/magic/effects.py:_dump_container_contents`
- **ROM C**: `src/effects.c:172,418` (`acid_effect`/`fire_effect` container dump)
- **Gap**: dumping a container that is itself inside another container stubbed the
  `obj->in_obj` branch to `extract_obj` (destroy) instead of ROM's
  `obj_to_obj(t_obj, obj->in_obj)` (spill to parent). A bag inside a chest hit by
  a fireball lost its contents to the void. (The audit had marked container
  dumping ✅ COMPLETE — a stale false-checkmark.)
- **Fix**: added `_get_obj_to_obj` lazy import; the `in_obj` branch routes through
  `_obj_to_obj` (head-insert, INV-039). Covers both `acid_effect` and
  `fire_effect` (shared helper).
- **Tests**: `tests/integration/test_environmental_effects.py::TestContainerDumpToParent`.

### `MobInstance.add_affect` — ✅ FIXED (GL-032 follow-up, v2.14.314)

- **Python**: `mud/spawning/templates.py:MobInstance.add_affect`
- **ROM C**: `src/handler.c:1018-1164` (`affect_modify`, uniform for PC/NPC)
- **Gap**: `Character.add_affect` applies `hitroll`/`damroll`/`saving_throw`
  kwargs; `MobInstance.add_affect` was a `**kwargs` stub that silently dropped
  them — the last asymmetry GL-032 left in the Character/MobInstance affect
  surface. Latent (no shipped caller passed modifiers to a mob) but a silent-drop
  footgun.
- **Fix**: made the signatures symmetric.
- **Tests**: `tests/integration/test_gl032_mob_affect_application.py::test_mob_add_affect_applies_stat_modifiers_like_character`.

### Docs correction — stale `FINDING-001` triage (no version bump)

- **File**: `tools/diff_harness/FINDINGS.md`
- Re-verified all four "next triage steps" of the `movement_get_drop`
  divergence as resolved: `mob_registry` `long_descr` count is deterministic
  (986 protos / 1 legitimately-empty `2006 "It"` in `catacomb.are`), Hassan proto
  (3011) `long_descr` loads correctly, the scenario converges (KNOWN_DIVERGENCES
  empty, 64/64 differential scenarios pass). Annotated the block closed.

### Verified-faithful probes (no change)

- **Follower/group disband** — `die_follower`/`stop_follower`/`add_follower`
  (`act_comm.c:1591-1680`): identity comparisons, charm-clear ordering, message
  gating, pet-release all match.
- **`gain_condition`** (`update.c:367`): clamp `[0,48]`, immortal/NPC/−1 guards,
  DRUNK "sober only if was non-zero" edge all match.
- **`weather_update`** (`update.c`): initially suspected absent — confirmed
  implemented as `weather_tick()` in `game_loop.py`; pressure math, RNG order
  (`dice(1,4)/dice(2,6)/dice(2,6)`), two-`if`-vs-`elif` sky machine, and
  `time_tick → weather_tick` call order all faithful.
- **`do_flee`** (`fight.c`): RNG stream (`number_door` + `number_range(0,daze)`
  only when `daze != 0`, matching ROM's no-draw `number_range(0,0)`), thief
  snuck-away, `gain_exp(-10)` all match.
- **`make_corpse` coin split** (`fight.c:1473-1497`): NPC `gold>0` gate, PC clan
  half-coin drop all match — the "approximation" comment was historical
  (FIGHT-079).

## Files Modified

- `mud/advancement.py`, `mud/math/stat_apps.py` — GL-049
- `mud/world/look.py` — LOOK-018
- `mud/magic/effects.py` — EFFECTS-006
- `mud/spawning/templates.py` — MobInstance.add_affect
- `tests/test_advancement.py`, `tests/integration/test_character_advancement.py`,
  `tests/integration/test_look_char_tags_show_char_to_char_0.py`,
  `tests/integration/test_environmental_effects.py`,
  `tests/integration/test_gl032_mob_affect_application.py` — new + updated tests
- `docs/parity/UPDATE_C_AUDIT.md` (GL-049), `ACT_INFO_C_AUDIT.md` (LOOK-018),
  `EFFECTS_C_AUDIT.md` (EFFECTS-006) — rows flipped ✅
- `tools/diff_harness/FINDINGS.md` — FINDING-001 triage closed
- `CHANGELOG.md` — 4 Fixed entries
- `pyproject.toml` — 2.14.310 → 2.14.314

## Test Status

- Per changed area (serial, green): advancement 47, character_advancement 21,
  environmental_effects 38, gl032/gl027/pet-save 9, look+furniture 30,
  differential smoke 64.
- Full suite: one parallel run aborted on an **xdist scheduler INTERNALERROR**
  (`KeyError: <WorkerController gw12>` during `worker_collectionfinish`) — an
  environmental xdist flake (zero `FAILED` lines), not a test failure. A prior
  full run this session completed at 6184 passed with only the 6 advancement
  assertions that GL-049 then updated. A clean re-run should be confirmed before
  pushing.

## Next Steps

1. **Confirm a clean full-suite run**, then **review + push** the local `master`
   commits (v2.14.298 → v2.14.314; 23 commits unpushed incl. the prior session's
   backlog). Push remains the gating user decision.
2. Continue the **self-admitted-divergence-marker sweep** — remaining unprobed
   markers: `mud/commands/build.py:2617/2637` (OLC spell-name lookup, Tier-C
   deferred), `mud/world/look.py:261` (IS_BUILDER TODO). Then resume
   divergence-class probes (`/rom-divergence-sweep`) or new `tools/diff_harness/`
   scenarios for un-covered surfaces.
