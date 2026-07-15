# Session Status — 2026-07-15 — DATABASE_URL CWD-relative persistence fix, pushed to master + PyPI

## Current State

- **Active focus**: **cross-file invariants / divergence-class probe** mode
  remains the parity default (per-file audit tracker at 100%, documented
  backlog drained) — unchanged from the prior session. This session was an
  out-of-band infra bug fix, not parity-audit work.
- **This run (v2.14.314 → v2.14.315):** user reported that characters
  created via the nanny menu vanished after a server restart. Root cause:
  `mud/config.py:DATABASE_URL` and `mud/db/session.py:DATABASE_URL` both
  defaulted to the **relative** SQLite URL `sqlite:///mud.db`, which resolves
  against the process's CWD at engine-construction time — restarting from a
  different working directory silently opened a different, empty database
  file. Fixed by anchoring both defaults to the repo root. Also fixed
  `docs/USER_GUIDE.md`/`docs/ADMIN_GUIDE.md`, which told operators to set
  `DATABASE_URL=sqlite:///quickmud.db` (wrong filename vs. the code's actual
  `mud.db` default). New regression test: `tests/test_database_url_config.py`.
- **Pointer to latest summary**:
  [SESSION_SUMMARY_2026-07-15_DATABASE_URL_CWD_PERSISTENCE_FIX.md](SESSION_SUMMARY_2026-07-15_DATABASE_URL_CWD_PERSISTENCE_FIX.md)
- **Prior parity session** (divergence-marker sweep, GL-049/LOOK-018/EFFECTS-006/`add_affect`):
  [SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md](SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md)

## Project Status (snapshot)

| Metric | Value |
|--------|-------|
| Version | 2.14.315 |
| Tests | **6204 passed, 4 skipped, 0 failed** — clean full parallel run (367s). (+2 tests vs. last session's 6202, from this session's new regression test.) |
| ROM C files audited | 43 / 43 |
| Push status | **Pushed to `origin/master`** this session (28 commits: 27 from the prior backlog + this session's fix), and published to PyPI. |
| Active focus | Cross-file invariants / divergence-class probe (documented backlog drained) |

## Outstanding — deferred by design

- **DESC-001** (latent) — unchanged; unreachable plain-replace description path.
- **OLC spell-name lookup** (`build.py:2617/2637`) — Tier-C deferred.
- **IS_BUILDER** (`look.py:261`) — TODO, area-builder subsystem not yet added.
- **Stray unused SQLite files** — `data/quickmud.db` (0 bytes) and
  `doc/game.db` (stale, 2025-09-04) found in the tree during this session's
  investigation; not deleted (no explicit confirmation for that specific
  destructive action). Confirm unused by any deployment, then clean up.

## Next Intended Task

Resume the **cross-file invariants / divergence-class probe** pass
(`/rom-divergence-sweep`) or author new `tools/diff_harness/` scenarios for
un-covered surfaces (mob-script trigger ordering, group/follower disband
edges, corpse/decay lifecycle) — same next task as the prior session, since
this session's work was an unplanned bug-report interrupt.
