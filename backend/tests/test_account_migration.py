"""Upgrade path: credentials stored on AppSetting must become the first Account."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Account, AppSetting, Base, Task
from app.security import encrypt_secret


async def _seed_legacy(db_url: str):
    """Create a database shaped like a v2.0.0 install (credentials on AppSetting)."""
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            AppSetting(
                api_id="12345678",
                api_hash_enc=encrypt_secret("legacy-hash"),
                phone="+8613800138000",
                session_enc=encrypt_secret("legacy-session"),
            )
        )
        session.add(Task(name="旧任务A", target_type="bot", bot_username="@a", action_type="message", message="/x"))
        session.add(Task(name="旧任务B", target_type="bot", bot_username="@b", action_type="message", message="/y"))
        await session.commit()
    await engine.dispose()


async def _run_migration(db_url: str):
    """Run the upgrade against the database and read the result back."""
    from app.database import _migrate_legacy_account

    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    await _migrate_legacy_account(factory)

    async with factory() as session:
        accounts = (await session.execute(select(Account))).scalars().all()
        tasks = (await session.execute(select(Task).order_by(Task.id))).scalars().all()
        settings = (await session.execute(select(AppSetting))).scalars().first()
    await engine.dispose()
    return accounts, tasks, settings


def test_legacy_credentials_become_the_first_account(tmp_path):
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    asyncio.run(_seed_legacy(db_url))
    accounts, tasks, settings = asyncio.run(_run_migration(db_url))

    assert len(accounts) == 1
    account = accounts[0]
    assert account.name == "默认账号"
    assert account.enabled is True
    assert account.api_id == "12345678"
    assert account.phone == "+8613800138000"
    assert account.api_hash_enc and account.session_enc  # carried over encrypted

    # every orphan task is adopted, so behaviour is unchanged after upgrading
    assert [task.account_id for task in tasks] == [account.id, account.id]

    # the stale plaintext-ish copies are cleared to avoid a second source of truth
    assert settings.api_id is None
    assert settings.api_hash_enc is None
    assert settings.phone is None
    assert settings.session_enc is None


def test_migration_is_idempotent(tmp_path):
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'twice.db').as_posix()}"
    asyncio.run(_seed_legacy(db_url))
    asyncio.run(_run_migration(db_url))
    accounts, tasks, _ = asyncio.run(_run_migration(db_url))

    # the second pass must not create a duplicate account
    assert len(accounts) == 1
    assert {task.account_id for task in tasks} == {accounts[0].id}


def test_no_legacy_data_creates_nothing(tmp_path):
    """A brand new install has no account until the user adds one."""
    db_url = f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}"

    async def _fresh():
        from app.database import _migrate_legacy_account

        engine = create_async_engine(db_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(AppSetting())
            await session.commit()

        await _migrate_legacy_account(factory)
        async with factory() as session:
            accounts = (await session.execute(select(Account))).scalars().all()
        await engine.dispose()
        return accounts

    assert asyncio.run(_fresh()) == []
