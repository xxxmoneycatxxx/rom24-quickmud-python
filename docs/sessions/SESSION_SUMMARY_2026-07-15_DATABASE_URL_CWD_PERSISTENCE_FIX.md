# Session Summary — 2026-07-15 — DATABASE_URL CWD-relative persistence bug

## Scope

User reported that characters created via the nanny menu only persisted for
the current running session and were gone after the MUD process was
restarted. This is an infrastructure/persistence bug, not a ROM parity gap —
no ROM C equivalent exists (ROM's flat-file pfiles have no analogous failure
mode), so this session followed `superpowers:systematic-debugging` +
`superpowers:test-driven-development` rather than the parity-audit workflow.

Root-cause investigation (delegated to an Explore subagent, Phase 1) traced
the full creation → save → load chain and found it internally consistent:
`create_character()` (`mud/account/account_service.py:988-1127`) commits
synchronously at creation time, and `save_character()` /
`load_character()` (`mud/account/account_manager.py`) both operate on the
same `SessionLocal`/`engine` bound to the same `characters` table. No
in-memory-SQLite default, no path/table mismatch between save and load.

The actual defect: both `mud/config.py:DATABASE_URL` and
`mud/db/session.py:DATABASE_URL` defaulted to the **relative** SQLite URL
`sqlite:///mud.db`. A relative SQLite path resolves against the process's
current working directory at engine-construction time, not the repo root —
so restarting the server from a different CWD (different shell, process
manager, container recreated without a persistent bind mount) opened a
*different*, empty database file. Physical evidence in the repo: three
distinct `.db` files existed simultaneously (`./mud.db`, `./data/quickmud.db`
empty, `./doc/game.db` stale), proof the server has been launched from
multiple different working directories over the project's life. Compounding
this: `docs/USER_GUIDE.md` / `docs/ADMIN_GUIDE.md` told operators to set
`DATABASE_URL=sqlite:///quickmud.db` — a different filename than the code's
actual `mud.db` default.

## Outcomes

### DATABASE_URL CWD-relative default — ✅ FIXED

- **Python**: `mud/config.py:14-20`, `mud/db/session.py:1-12`
- **ROM C**: N/A (architectural divergence — ROM's `save.c` pfiles are
  addressed by an absolute `PLAYER_DIR` constant compiled into the binary;
  there is no direct C equivalent of a relative-CWD SQLite URL).
- **Fix**: both modules now anchor the default to the repo root
  (`Path(__file__).resolve().parent[.parent].parent`) instead of a bare
  relative `sqlite:///mud.db` string, so the resolved path is identical
  regardless of the launching process's CWD. `mud/config.py`'s existing
  `_CONFIG_PATH` (qmconfig.rc) was refactored to reuse the same `_REPO_ROOT`
  constant rather than recomputing `Path(__file__).resolve().parent.parent`
  a second time.
- **Docs**: `docs/USER_GUIDE.md:532` and 6 occurrences in
  `docs/ADMIN_GUIDE.md` changed `quickmud.db` → `mud.db` to match the actual
  code default.
- **Tests**: `tests/test_database_url_config.py` (2 new tests) — asserts
  both `mud.config.DATABASE_URL` and `mud.db.session.DATABASE_URL` resolve
  to the same absolute path when the module is imported from two different
  working directories (repo root vs. a `tmp_path`), with `dotenv.load_dotenv`
  stubbed out so the repo's real `.env` (which pins an explicit override)
  doesn't mask the fallback-default behavior under test. Watched RED
  (`AssertionError: assert False ... is_absolute()`) before the fix, GREEN
  after.

## Files Modified

- `mud/config.py` — `DATABASE_URL` default anchored to repo root; `_CONFIG_PATH` reuses the new `_REPO_ROOT`.
- `mud/db/session.py` — `DATABASE_URL` default anchored to repo root (independent computation, same fix).
- `tests/test_database_url_config.py` — new regression test (2 cases).
- `docs/USER_GUIDE.md`, `docs/ADMIN_GUIDE.md` — `quickmud.db` → `mud.db` (7 occurrences) to match code default.
- `CHANGELOG.md` — added `### Fixed` entry under `[Unreleased]`.
- `pyproject.toml` — 2.14.314 → 2.14.315 (patch: bugfix, no API surface change).

## Test Status

- `pytest -n0 tests/test_database_url_config.py` — 2/2 passing (watched RED → GREEN).
- Full suite: `pytest` (parallel) — **6204 passed, 4 skipped, 0 failed** (367s). An earlier run hit the documented xdist sessionfinish teardown `INTERNALERROR` (`KeyError: <WorkerController gwNN>` in `xdist/scheduler/loadscope.py`) with a stray "1 failed" in the truncated tail output; re-run without truncation confirmed exit code 0 and 0 failed — consistent with the known-harmless flake documented in this project's build notes, not a real regression.
- `ruff check` / `ruff format --check` on touched files — clean.
- `gitnexus_impact(DATABASE_URL, upstream)` — risk LOW, 0 upstream dependents (module-level constant, no other module imports `mud.config.DATABASE_URL` directly).
- `gitnexus_detect_changes(scope=all)` — risk LOW, 0 affected execution flows.

## Next Steps

This was an out-of-band infra fix triggered by a user bug report, not a
parity-audit pass — no tracker rows to flip. The per-file audit tracker
remains at 43/43 (P0/P1/P2 100%, P3 75% + 3 N/A) per the last parity
session; cross-file invariants / divergence-class sweep remains the active
parity mode for the next session (`docs/parity/DIVERGENCE_CLASS_ROSTER.md`).

Separately, two stray SQLite files were found unused in the tree
(`data/quickmud.db` — 0 bytes, `doc/game.db` — stale from 2025-09-04). They
were **not** deleted this session (no explicit user confirmation for that
specific destructive action) — worth a follow-up cleanup once confirmed
unused by any deployment.

This session also pushed a backlog of 27 previously-local, already-committed
commits (2026-07-10 divergence-marker sweep + prior sessions) that had been
sitting on `master` unpushed — see
[SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md](SESSION_SUMMARY_2026-07-10_DIVERGENCE_MARKER_SWEEP.md)
and earlier summaries in this directory for their individual content.
