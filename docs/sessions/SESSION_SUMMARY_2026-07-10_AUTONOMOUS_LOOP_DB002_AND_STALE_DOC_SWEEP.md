# Session Summary — 2026-07-10 — Autonomous 10-iteration loop: DB-002 pet-affect dedup + stale-doc reconciliation + faithful-verify probes

## Scope

Continued the autonomous parity loop from the prior "backlog drain" session
(`SESSION_STATUS` pointed at
`SESSION_SUMMARY_2026-07-10_AUTONOMOUS_LOOP_BACKLOG_DRAIN.md`). With the per-file
audit tracker at 100% and the documented minor-gap backlog drained, this run
operated in the **cross-file invariants / divergence-class probe** mode: pick a
candidate contract, read ROM C, read the Python equivalent, and either close a
real divergence (failing-test-first) or record a converged (ROM-faithful) probe.

Ran 10 iterations. The dominant, honest finding: **the documented and
reachable-probe surface is genuinely drained** — of 7 substantive divergence
probes across 4 divergence classes, only one surfaced a real code gap (DB-002).
The rest were either already faithful (and their trackers merely stale) or
verified bit-for-bit correct. One real code fix, one pre-existing test-isolation
fix, three stale-doc reconciliations, four faithful-verified probes.

## Outcomes

### `DB-002` — ✅ FIXED (pet-affect load dedup)

- **Python**: `mud/db/serializers.py` `_deserialize_pet`
- **ROM C**: `src/db.c:3938` `check_pet_affected`, called from `fread_pet`
  `src/save.c:1567`
- **Gap**: ROM drops a loaded pet affect **iff** `paf->where == TO_AFFECTS`
  **and** `IS_AFFECTED(get_mob_index(vnum), paf->bitvector)` — a non-zero AND
  test against the pet **prototype's inherent** `affected_by` bitfield (the
  JR-2002 fix; without it, re-adding then wearing off a prototype-inherent bit
  strips the inherent flag via `affect_modify`). The Python port deduped on a
  `(type, location, modifier)` match against the prototype's `affected` **list**,
  ignoring both `where` and `bitvector` — a different field and criterion, so the
  ROM dedup never fired.
- **Fix**: `_deserialize_pet` captures the prototype's inherent `affected_by`
  right after `spawn_mob` (before the saved runtime value overwrites it) and
  applies ROM's exact criterion.
- **Tests**: `tests/integration/test_db002_check_pet_affected.py` (1 test, 3
  assertions: dedup on inherent bit; kept when bit absent; kept when
  `where != TO_AFFECTS`). Plus GL-031/GL-032 pet round-trips still green.

### Test isolation — ✅ FIXED (`test_new_character_persists_true_sex`)

- **Python**: `tests/test_account_auth.py:1121`
- **Gap**: pre-existing cross-file isolation bug (predates this session). The
  test sets `char.room`/`was_in_room`, saves, reloads, and asserts
  `reloaded.room` resolves — which needs `room_registry` populated. It never
  called `initialize_world()`, so it passed only when a sibling test loaded the
  world first; it failed under `-n0` or `-k` selection.
- **Fix**: added `initialize_world("area/area.lst")` to the test setup per the
  AGENTS.md parallel-safety rule ("a test must pass when run alone"). No engine
  change.

### Stale-doc reconciliations (re-verify rule) — ✅ corrected

Three audit docs carried `❌`/`⚠️ Partial`/"stub" status markers contradicting
their own gap-detail rows, which recorded the gaps as ✅ FIXED with tests. Each
was re-verified against ROM C + the Python source before flipping:

- **`interp.c:check_social`** — the summary + Phase-3 rows called
  `perform_social` a "stub" missing COMM_NOEMOTE / position gates / snore
  exception / NPC slap auto-react. It is a faithful port (`socials.py:38-118`);
  INTERP-018/019/020/021/022/023/035 all ✅ FIXED; 32 socials tests pass.
- **`interp.c` summary + Phase-4 planning** — `cmd_table`/`interpret` rows still
  read "⚠️ Partial — many trust/position/dispatch divergences" and "missing
  snoop, wiznet log, empty-input semantics", and the recommended-close list
  framed ~13 INTERP IDs as open. Every INTERP-NNN gap is ✅ FIXED (INTERP-003
  wiznet VERIFIED, INTERP-016 `tail_chain` CLOSED-DEFERRED as a stock-ROM no-op).
- **`db2.c` Phase-1 inventory** — `❌` markers on the act/affected_by/off/imm/
  res/vuln/form/parts/ac/long_descr rows for gaps the header + gap table list as
  ✅ FIXED (DB2-001/002/003/006). `merge_race_flags` ORs the race-table flag
  sets, `from_prototype` letter-decodes them to int, `ac*10` and first-char UPPER
  are applied by both loaders.

### Faithful-verified probes (converged — no code change)

Recorded for provenance; each read ROM C against the Python equivalent and found
bit-for-bit parity:

- **`compute_thac0`** (`mud/combat/engine.py:1761`) vs ROM `fight.c` — all four
  signed-division sites use `c_div` (th<0 halving, th<-5 halving, `hitroll*skill/
  100`, `5*(100-skill)/100`).
- **`xp_compute`** (`mud/groups/xp.py:135`) vs ROM `fight.c` `xp_compute` — the
  order-dependent chained integer divisions (`(align-500)*base_exp/500*level/
  total_levels`, `time_per_level`, final `xp*level/(total_levels-1)`) are
  preserved as nested `c_div`; signed `gch_alignment` else-branch handled; all
  align-multiplier branches match. ARITH-005..008 cited in-source.
- **`obj_update`** decay (`mud/game_loop.py:1497`) vs ROM `update.c` — timer
  semantics, the subtle spill gate (contents preserved only for `CORPSE_PC` or
  runtime `wear_loc == FLOAT`; NPC-corpse contents destroyed), shopkeeper
  `cost//5`, and the PIT (`OBJ_VNUM_PIT == 3010`, no-TAKE) no-broadcast special
  all faithful (GL-018/GL-040 cited).
- **Combat victim-AC rescale** (`_compute_victim_ac`, `engine.py:540`) — the
  signed `c_div(victim_ac + 15, 5) - 15` /10-scale handling is ROM-faithful
  (FIGHT-081 cited).

## Files Modified

- `mud/db/serializers.py` — DB-002: `_deserialize_pet` captures prototype
  `affected_by` and applies ROM `check_pet_affected` criterion.
- `tests/integration/test_db002_check_pet_affected.py` — new (DB-002 regression).
- `tests/test_account_auth.py` — `initialize_world()` in
  `test_new_character_persists_true_sex` setup.
- `docs/parity/DB_C_AUDIT.md` — `check_pet_affected` row + DB-002 detail →
  ✅ FIXED.
- `docs/parity/ROM_C_SUBSYSTEM_AUDIT_TRACKER.md` — db.c note updated (DB-002).
- `docs/parity/INTERP_C_AUDIT.md` — stale summary/Phase-3/Phase-4 rows → COMPLETE.
- `docs/parity/DB2_C_AUDIT.md` — stale `❌` inventory rows → ✅ FIXED.
- `CHANGELOG.md` — DB-002 + test-isolation entries.
- `pyproject.toml` — 2.14.307 → 2.14.309.

## Commits (this session, all LOCAL / UNPUSHED on `master`)

```
dcdbcdbc test: make test_new_character_persists_true_sex self-contained
b0f83b59 docs(parity): db2.c — flip stale ❌ inventory rows to ✅ FIXED
8cb96abe docs(parity): interp.c — flip stale summary + Phase-4 planning to COMPLETE
99470c6a fix(parity): db.c:DB-002 — pet-affect load dedup matches check_pet_affected
40dfabdd docs(parity): interp.c:check_social rows — flip stale ❌/stub to ✅ FIXED
```

## Test Status

- `test_db002_check_pet_affected.py`, GL-031/GL-032, pet round-trip, socials,
  and the three Layer-A grep-guards (`test_rng_determinism`,
  `test_equipment_key_convention`, `test_attribute_convention`,
  `test_message_delivery_convention`) — all green (44 in the focused subset).
- Full suite: run at session end; see `SESSION_STATUS.md` for the number.

## Next Steps

The documented per-file backlog and the obvious divergence-class probes are
drained. Remaining real-divergence discovery requires either (a) authoring **new
`tools/diff_harness/` scenarios** for un-covered engine surfaces (mob-script
trigger ordering, group/follower disband edges, corpse/decay lifecycle beyond
the existing scenarios), or (b) deep-reading a specific ROM function nobody has
diffed. A recurring cost worth addressing systematically: several audit docs
carry stale `❌`/"stub" status markers for gaps their own detail rows record as
FIXED — a broader one-pass reconciliation across `docs/parity/*_C_AUDIT.md`
would stop future agents re-discovering "open" gaps that are already closed.

**Gating action unchanged**: the v2.14.298 → v2.14.309 commits are all local on
`master`, awaiting user review + push.
