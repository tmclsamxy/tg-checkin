"""SQLAlchemy async engine / session helpers."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import Column, event, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

logger = logging.getLogger(__name__)

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

    await _migrate_legacy_account()


async def _migrate_legacy_account(session_factory: Any = None) -> None:
    """Move the pre-multi-account credentials into the first Account row.

    Up to v2.0.0 the Telegram credentials lived on the single AppSetting row.
    Reading them is kept for upgrades only; afterwards the columns are cleared
    so a stale copy can never be mistaken for a live login.

    ``session_factory`` defaults to the application session maker; tests inject
    their own so the upgrade path can be exercised on a scratch database.
    """
    from .models import Account, AppSetting, Task

    factory = session_factory or SessionLocal

    async with factory() as session:
        existing = (await session.execute(select(Account).limit(1))).scalars().first()
        if existing is not None:
            return

        rows = (await session.execute(select(AppSetting).order_by(AppSetting.id))).scalars().all()
        legacy = next(
            (row for row in rows if row.api_id or row.session_enc or row.phone), None
        )
        if legacy is None:
            return

        account = Account(
            name="默认账号",
            enabled=True,
            sort_order=0,
            api_id=legacy.api_id,
            api_hash_enc=legacy.api_hash_enc,
            phone=legacy.phone,
            session_enc=legacy.session_enc,
        )
        session.add(account)
        await session.flush()

        # Adopt the orphan tasks so their behaviour is unchanged after upgrade.
        tasks = (await session.execute(select(Task).where(Task.account_id.is_(None)))).scalars().all()
        for task in tasks:
            task.account_id = account.id

        legacy.api_id = None
        legacy.api_hash_enc = None
        legacy.phone = None
        legacy.session_enc = None
        await session.commit()

        logger.info(
            "已把原有 Telegram 凭据迁移为账号「%s」，%s 个任务已归属该账号",
            account.name,
            len(tasks),
        )


async def _ensure_columns() -> None:
    """Add columns introduced after the initial release (SQLite only)."""
    from .models import Account, AppSetting, Task, RunLog

    async with engine.begin() as conn:
        for model in (Account, Task, AppSetting, RunLog):
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
