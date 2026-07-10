# Session Status — 2026-07-10 — Autonomous /loop backlog drain COMPLETE (9 gaps + live crash, LOCAL/UNPUSHED)

## Current State

- **Active focus**: the documented per-file gap backlog is now **drained**. With
  the per-file audit tracker at 100% (no ⚠️ Partial / ❌ Not Audited rows) and the
  minor-gap backlog closed, the next active mode is the **cross-file invariants /
  divergence-class** pass (probe-then-scope; see AGENTS.md "Cross-File Invariants"
  and `docs/parity/DIVERGENCE_CLASS_ROSTER.md`).
- **This run (v2.14.298 → v2.14.307, all committed LOCALLY on `master`, NOT
  pushed):** 9 `fix(parity)` commits + 1 `docs(parity)` policy commit. A 10-iteration
  autonomous loop that drained the remaining documented gap backlog and fixed a
  **live `inventory`/`equipment` crash** the user reported mid-session.
  - **AURA-001** (live crash) — `_char_affected` imported a non-existent
    `skill_lookup`; rewritten to ROM's `IS_AFFECTED(ch, AFF_DETECT_*)` bitfield test.
  - **DROP-001 + WIMPY-002** — new shared `rom_is_number`/`rom_atoi` helpers
    (C `is_number`/`atoi`); the `is_number`/`atoi` class is now fully closed.
  - **STEAL-001** — `do_steal` now calls `check_improve` on all three ROM paths.
  - **RESCUE-002** — `rescue` renders NPC parties via ROM `act_format`/PERS.
  - **TRIP-002** — `do_trip` miss no longer double-delivers (void; failure returns "").
    The "size shift ~7 not 20" suspicion was resolved as a `check_improve` sweep
    artifact — the size modifier is ROM-correct (10 per step).
  - **PUT-006** — `do_put` container is `arg2` (second token), not the last word.
  - **LOCK-003** — door lock/unlock key guard uses ROM `key < 0` (was `<= 0`).
  - **GIVE-006** — worn-item give reports ROM's "You do not have that item."
    (strict parity; revertible).
  - **ROM-FAITHFUL directive** — added to AGENTS.md at the user's request.
- **Pointer to latest summary**:
  [SESSION_SUMMARY_2026-07-10_AUTONOMOUS_LOOP_BACKLOG_DRAIN.md](SESSION_SUMMARY_2026-07-10_AUTONOMOUS_LOOP_BACKLOG_DRAIN.md)

## Project Status (snapshot)

| Metric | Value |
|--------|-------|
| Version | 2.14.307 |
| Tests | **6186 passed, 4 skipped** (full parallel run, 278s, zero failures) |
| ROM C files audited | 43 / 43 |
| Push status | **All local on `master`, UNPUSHED** — awaiting user review |
| Active focus | Cross-file invariants / divergence-class pass (per-file backlog drained) |

## Outstanding — deferred by design

- **DESC-001** (latent) — ROM's plain-replace description path has no length guard;
  Python rejects a ≥1024-char plain replace. Unreachable while `MAX_INPUT_LENGTH ==
  256` (a single `description` command can't reach 1024 chars). Removing the Python
  guard drops a harmless safety cap for zero parity benefit — left as-is by design;
  revisit only if the input layer starts accepting single commands ≥1024 chars.

## Next Intended Task

1. **Review + push** the `v2.14.299 → v2.14.307` commits (all local on `master`).
   This is the gating next action.
2. Resume the **cross-file invariants / divergence-class** pass: pick a candidate
   area not yet covered by an INV row (affect ticks, position transitions,
   mob-script triggers, group/follower chains), run a 5-minute probe (read ROM C
   contract → read Python equivalent → write one failing test), then close as a
   gap (single commit) or file as the next free INV-NNN.
