"""Regression test for the "characters vanish after MUD restart" bug.

Root cause (2026-07-15 session): both ``mud.config.DATABASE_URL`` and
``mud.db.session.DATABASE_URL`` defaulted to the *relative* SQLite URL
``sqlite:///mud.db``. A relative SQLite path resolves against the process's
current working directory at engine-construction time, not the repo root —
so starting the server from a different directory (a different shell, a
process manager, a container without a bind mount) silently opens/creates a
*different* database file. Characters created in one run become invisible
the moment the next run's effective CWD differs, even though nothing was
actually deleted.

The fix anchors the default to the repo root so the resolved path is
identical regardless of the process's CWD.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import dotenv


def _reload_default(monkeypatch, module_name: str, cwd: Path):
    # Isolate the module's *fallback* default from this repo's real .env
    # (which pins DATABASE_URL=sqlite:///mud.db) — python-dotenv's
    # load_dotenv() searches upward from CWD and would otherwise leak that
    # explicit override into a "no env var set" test.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_args, **_kwargs: False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(cwd)
    module = importlib.import_module(module_name)
    return importlib.reload(module)


def test_config_database_url_default_is_cwd_independent(monkeypatch, tmp_path):
    from mud import config

    repo_root = Path(config.__file__).resolve().parent.parent
    try:
        module = _reload_default(monkeypatch, "mud.config", repo_root)
        expected = module.DATABASE_URL

        module = _reload_default(monkeypatch, "mud.config", tmp_path)
        assert module.DATABASE_URL == expected
        assert Path(module.DATABASE_URL.removeprefix("sqlite:///")).is_absolute()
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_db_session_database_url_default_is_cwd_independent(monkeypatch, tmp_path):
    from mud.db import session

    repo_root = Path(session.__file__).resolve().parent.parent.parent
    try:
        module = _reload_default(monkeypatch, "mud.db.session", repo_root)
        expected = module.DATABASE_URL

        module = _reload_default(monkeypatch, "mud.db.session", tmp_path)
        assert module.DATABASE_URL == expected
        assert Path(module.DATABASE_URL.removeprefix("sqlite:///")).is_absolute()
    finally:
        monkeypatch.undo()
        importlib.reload(session)
