# Session Status — 2026-07-10 — Autonomous 10-iteration loop: DB-002 + stale-doc sweep (LOCAL/UNPUSHED)

## Current State

- **Active focus**: **cross-file invariants / divergence-class probe** mode. The
  per-file audit tracker is at 100% and the documented minor-gap backlog is
  drained; this run confirmed (across 7 substantive probes in 4 divergence
  classes) that the documented and reachable-probe surface is genuinely
  exhausted — only one probe surfaced a real code gap.
- **This run (v2.14.307 → v2.14.309, all committed LOCALLY on `master`, NOT
  pushed):** 1 `fix(parity)` (DB-002), 1 `test:` (isolation fix), 3
  `docs(parity)` stale-marker reconciliations.
  - **DB-002** (real fix) — `_deserialize_pet` pet-affect load dedup now matches
    ROM `check_pet_affected` (`where == TO_AFFECTS` AND prototype-inherent
    `affected_by & bitvector`), replacing a non-ROM `(type, location, modifier)`
    list scan. The JR-2002 pet-affect-duplication class is now closed.
  - **Test isolation** — `test_new_character_persists_true_sex` now calls
    `initialize_world()` so it passes run-alone (was a latent cross-file
    dependency; pre-existing, not caused by this session).
  - **Stale-doc corrections** — `interp.c:check_social` (faithful port, not a
    stub), `interp.c` summary + Phase-4 (all INTERP-NNN ✅), `db2.c` inventory
    rows (DB2-001/002/003/006 ✅).
  - **Faithful-verified probes** (no change): `compute_thac0`, `xp_compute`,
    `obj_update` decay, combat victim-AC rescale.
- **Pointer to latest summary**:
  [SESSION_SUMMARY_2026-07-10_AUTONOMOUS_LOOP_DB002_AND_STALE_DOC_SWEEP.md](SESSION_SUMMARY_2026-07-10_AUTONOMOUS_LOOP_DB002_AND_STALE_DOC_SWEEP.md)

## Project Status (snapshot)

| Metric | Value |
|--------|-------|
| Version | 2.14.310 |
| Tests | **6187 passed, 4 skipped** (full parallel run, 365s, zero failures) |
| ROM C files audited | 43 / 43 |
| Push status | **All local on `master`, UNPUSHED** — awaiting user review |
| Active focus | Cross-file invariants / divergence-class probe (documented backlog drained) |

## Outstanding — deferred by design

- **DESC-001** (latent) — unchanged from prior session; ROM's plain-replace
  description path has no length guard while `MAX_INPUT_LENGTH == 256` makes it
  unreachable. Left as-is by design.

## Next Intended Task

1. **Review + push** the `v2.14.298 → v2.14.309` commits (all local on `master`).
   This remains the gating next action.
2. Real-divergence discovery now needs **new probes**, not backlog consumption:
   author `tools/diff_harness/` scenarios for un-covered surfaces (mob-script
   trigger ordering, group/follower disband edges, corpse/decay lifecycle) or
   deep-read a specific un-diffed ROM function.
3. ~~**Systematic hygiene opportunity**: audit-doc stale-marker reconciliation.~~
   **DONE (2026-07-10, 2.14.310).** One-pass sweep across 14
   `docs/parity/*_C_AUDIT.md` (6 read-only agents; every flip verified against the
   doc's own ✅ FIXED detail row + code/tests for code-backed claims) corrected ~50
   summary/inventory/phase rows that showed `❌`/`⚠️`/`stub` for already-FIXED gaps.
   Genuinely-open markers (SPLIT-001, do_mpat, medit_show sub-gaps, help_lookup, OLC
   Tier-C) deliberately left. See CHANGELOG. Future audits should keep summary rows
   in sync with detail rows at closure time to avoid re-accumulating this drift.
