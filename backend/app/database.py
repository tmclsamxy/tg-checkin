"""SQLAlchemy async engine / session helpers."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, text
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
    from .models import Task

    async with engine.begin() as conn:
        res = await conn.execute(text("PRAGMA table_info(tasks)"))
        existing = {row[1] for row in res.fetchall()}
        table = Task.__table__
        for column in table.columns:
            if column.name not in existing:
                ddl = text(f'ALTER TABLE tasks ADD COLUMN "{column.name}" {column.type.compile()}')
                await conn.execute(ddl)


async def dispose_db() -> None:
    await engine.dispose()
