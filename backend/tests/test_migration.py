"""Verify the light-weight SQLite column migration used on upgrades."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("DATA_DIR", str(BACKEND_DIR.parent / ".pytest-data"))

from app.database import _add_column_sql  # noqa: E402
from app.models import AppSetting, Task  # noqa: E402


def _old_database() -> sqlite3.Connection:
    """A pre-upgrade database: the v2.0.0 schema without the captcha columns."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        'CREATE TABLE "tasks" (id INTEGER PRIMARY KEY, name VARCHAR(128), enabled BOOLEAN)'
    )
    conn.execute('CREATE TABLE "app_settings" (id INTEGER PRIMARY KEY, schedule_time VARCHAR(16))')
    conn.execute('INSERT INTO "tasks" (id, name, enabled) VALUES (1, \'旧任务\', 1)')
    conn.execute('INSERT INTO "app_settings" (id, schedule_time) VALUES (1, \'08:00\')')
    return conn


def test_new_columns_are_added_with_defaults():
    conn = _old_database()

    for column in (Task.__table__.c.auto_captcha, AppSetting.__table__.c.captcha_enabled):
        conn.execute(_add_column_sql(column))
    for column in (
        AppSetting.__table__.c.captcha_max_rounds,
        AppSetting.__table__.c.captcha_wait_seconds,
    ):
        conn.execute(_add_column_sql(column))

    # existing rows must be backfilled, not left NULL
    assert conn.execute('SELECT auto_captcha FROM "tasks"').fetchone() == (1,)
    assert conn.execute('SELECT captcha_enabled FROM "app_settings"').fetchone() == (1,)
    assert conn.execute('SELECT captcha_max_rounds FROM "app_settings"').fetchone() == (2,)
    assert conn.execute('SELECT captcha_wait_seconds FROM "app_settings"').fetchone() == (5,)

    # the pre-existing data is untouched
    assert conn.execute('SELECT name, schedule_time FROM "tasks", "app_settings"').fetchone() == (
        "旧任务",
        "08:00",
    )
    conn.close()


def test_generated_ddl_is_well_formed():
    assert _add_column_sql(Task.__table__.c.auto_captcha) == (
        'ALTER TABLE "tasks" ADD COLUMN "auto_captcha" BOOLEAN DEFAULT 1'
    )
    assert _add_column_sql(AppSetting.__table__.c.captcha_max_rounds) == (
        'ALTER TABLE "app_settings" ADD COLUMN "captcha_max_rounds" INTEGER DEFAULT 2'
    )
