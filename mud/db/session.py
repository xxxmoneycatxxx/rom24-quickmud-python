import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Anchor the default SQLite path to the repo root rather than leaving it
# relative — see mud/config.py for the full rationale (relative SQLite URLs
# resolve against the process's CWD at import time, not the repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_REPO_ROOT / 'mud.db'}")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
