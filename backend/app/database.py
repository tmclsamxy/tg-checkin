"""SQLAlchemy async engine / session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import Column, event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:  # pragma: no cover
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables (idempotent) and apply light-weight column migrations."""
    from .models import Base  # local import avoids circular dependency

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if settings.database_url.startswith("sqlite"):
        await _ensure_columns()


async def _ensure_columns() -> None:
    """Add columns introduced after the initial release (SQLite only)."""
    from .models import AppSetting, Task

    async with engine.begin() as conn:
        for model in (Task, AppSetting):
            table = model.__table__
            res = await conn.execute(text(f'PRAGMA table_info("{table.name}")'))
            existing = {row[1] for row in res.fetchall()}
            if not existing:
                continue  # table was just created with every column
            for column in table.columns:
                if column.name not in existing:
                    await conn.execute(text(_add_column_sql(column)))


def _add_column_sql(column: Column[Any]) -> str:
    """Build an ``ALTER TABLE ... ADD COLUMN`` statement that backfills defaults.

    SQLite requires a literal default when adding a column to a populated
    table; without it every existing row would end up ``NULL`` and ORM defaults
    only apply to newly inserted rows.
    """
    sql = f'ALTER TABLE "{column.table.name}" ADD COLUMN "{column.name}" {column.type.compile()}'
    default = column.default
    if default is not None and getattr(default, "is_scalar", False):
        value = default.arg
        if isinstance(value, bool):
            sql += f" DEFAULT {1 if value else 0}"
        elif isinstance(value, (int, float)):
            sql += f" DEFAULT {value}"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            sql += f" DEFAULT '{escaped}'"
    return sql


async def dispose_db() -> None:
    await engine.dispose()
