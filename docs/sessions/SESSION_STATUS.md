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
| Tests | Per-area green (advancement 47, char_advancement 21, env_effects 38, gl032/gl027 9, look+furniture 30, differential 64). Full **serial** run confirmed **0 failures** (parallel runs flaked on an xdist scheduler INTERNALERROR — environmental, not a test failure). |
| ROM C files audited | 43 / 43 |
| Push status | **All local on `master`, UNPUSHED** (23 commits incl. prior backlog) — awaiting user review |
| Active focus | Cross-file invariants / divergence-class probe (documented backlog drained) |

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
