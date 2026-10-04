"""Shared test setup.

Every run gets a brand new ``DATA_DIR`` **inside the workspace**, so a stale
database from a previous run (e.g. one where the password was changed by
``test_change_password``) can never break the suite. Keeping it in the project
also avoids writing to the system temp folder.

The environment has to be prepared before ``app`` is imported anywhere, which
is why this lives in conftest.py.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# `.pytest-data/` is gitignored; each run owns a unique child directory.
ROOT = PROJECT_DIR / ".pytest-data"
DATA_DIR = ROOT / f"run-{int(time.time())}-{os.getpid()}"
DATA_DIR.mkdir(parents=True, exist_ok=True)

os.environ["DATA_DIR"] = str(DATA_DIR)
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-pass-12345"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"


def _prune_old_runs(keep: int = 3) -> None:
    """Best-effort housekeeping; never fail the suite over it."""
    try:
        runs = sorted(
            (item for item in ROOT.iterdir() if item.is_dir() and item != DATA_DIR),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in runs[keep:]:
            shutil.rmtree(stale, ignore_errors=True)
    except Exception:  # pragma: no cover - housekeeping only
        pass


_prune_old_runs()
