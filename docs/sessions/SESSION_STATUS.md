# Session Status — 2026-07-10 — Divergence-marker sweep: 4 fixes + faithful-probe loop (LOCAL/UNPUSHED)

## Current State

- **Active focus**: **cross-file invariants / divergence-class probe** mode
  (per-file audit tracker at 100%, documented backlog drained). This run added a
  high-yield technique: **grep `mud/` for self-admitted divergence markers**
  ("not yet ported", "simplified version", "approximation") — a code comment
  confessing a divergence is an un-IDed pre-filed gap. Three of four fixes came
  from that sweep.
- **This run (v2.14.310 → v2.14.314, committed LOCALLY on `master`, NOT pushed):**
  4 `feat/fix(parity)` + 1 `docs(diff)`.
  - **GL-049** — `advance_level` mana/move now use ROM's stat-scaled
    `number_range` rolls (`src/update.c:81-95`), fixing both wrong per-level values
    and a 2-draw RNG desync per level-up.
  - **LOOK-018** — `show_char_to_char_0` now renders the furniture branch of the
    position suffix ("is sitting on a wooden chair.", `src/act_info.c:304-401`).
  - **EFFECTS-006** — acid/fire dumping a nested container now spills contents to
    the parent container instead of destroying them (`src/effects.c:172,418`).
  - **MobInstance.add_affect** — now applies hitroll/damroll/saving_throw
    modifiers, symmetric with `Character.add_affect` (GL-032 follow-up; latent).
  - **Docs** — closed the stale `FINDING-001` `movement_get_drop` triage block in
    `tools/diff_harness/FINDINGS.md` (all four steps re-verified resolved).
  - **Test hardening** — scoped `test_kill_mob_grants_xp_integration`'s
    `number_bits=19` pin to `width==5`, defusing a pre-existing `spec_cast_mage`
    infinite-loop landmine.
- **Faithful-verified probes (no change):** `die_follower`/`stop_follower`/
  `add_follower`, `gain_condition`, `weather_update`, `do_flee`, `make_corpse`
  coin split.
- **Pointer to latest summary**:
  [SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md](SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md)

## Project Status (snapshot)

| Metric | Value |
|--------|-------|
| Version | 2.14.314 |
| Tests | **6200 passed, 4 skipped** in the full serial run (`-n0`), plus **2 serial-only RNG-order flakes** (`test_mobprog_triggers::test_event_hooks_fire_rom_triggers`, `test_skills_combat::test_trip_knocks_target_wait_daze_and_improve`) that PASS in the default parallel CI mode and in isolation (`-n0` on each) — see Outstanding. Parallel full runs flaked on a machine-local xdist scheduler INTERNALERROR (environmental). |
| ROM C files audited | 43 / 43 |
| Push status | **All local on `master`, UNPUSHED** (23 commits incl. prior backlog) — awaiting user review |
| Active focus | Cross-file invariants / divergence-class probe (documented backlog drained) |

## Outstanding — filed this session

- **2 serial-only RNG-order-fragile tests** (surfaced by the full `-n0` run):
  `tests/test_mobprog_triggers.py::test_event_hooks_fire_rom_triggers` and
  `tests/test_skills_combat.py::test_trip_knocks_target_wait_daze_and_improve`.
  Both **pass in the default parallel CI mode and run in isolation** — they only
  fail in a full serial run because they read the ambient global Mitchell-Moore
  stream without seeding it locally, so any upstream change to draw counts (e.g.
  GL-049's +2 draws per level-up) shifts their outcome in single-process serial
  order. Not a shipped regression (CI runs parallel). **Fix direction:** add a
  local `rng_mm.seed_mm(<seed>)` in each test after fixture setup so the assertion
  is deterministic regardless of stream position (the AGENTS.md test-determinism
  rule). Low priority — file, don't block.

## Outstanding — deferred by design

- **DESC-001** (latent) — unchanged; unreachable plain-replace description path.
- **OLC spell-name lookup** (`build.py:2617/2637`) — Tier-C deferred.
- **IS_BUILDER** (`look.py:261`) — TODO, area-builder subsystem not yet added.

## Next Intended Task

1. **Review + push** the local `master` commits (v2.14.298 → v2.14.314; 23
   commits unpushed incl. the prior session's backlog). Push remains the gating
   user decision. Confirm one clean full-suite run first (the serial run this
   session showed 0 failures; parallel runs were flaking on a machine-local xdist
   scheduler bug — re-run parallel once the machine settles, or push on the serial
   green).
2. Continue the **self-admitted-divergence-marker sweep** (remaining markers are
   Tier-C/deferred), then resume divergence-class probes (`/rom-divergence-sweep`)
   or author new `tools/diff_harness/` scenarios for un-covered surfaces
   (mob-script trigger ordering, group/follower disband edges, corpse/decay
   lifecycle).
