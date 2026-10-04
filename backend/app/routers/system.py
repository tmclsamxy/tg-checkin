"""System / health endpoints."""

from __future__ import annotations

import platform
import time
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..deps import get_current_user, get_db
from ..models import Account, Task, User
from ..scheduler import checkin_scheduler
from ..schemas import SystemInfo
from ..settings_store import get_app_settings
from ..telegram.manager import telegram_manager

router = APIRouter(prefix="/api/system", tags=["system"])
_STARTED_AT = time.time()


@router.get("/info", response_model=SystemInfo)
async def info(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    total = await session.scalar(select(func.count(Task.id))) or 0
    enabled = await session.scalar(select(func.count(Task.id)).where(Task.enabled.is_(True))) or 0
    account_total = await session.scalar(select(func.count(Account.id))) or 0
    return SystemInfo(
        version=settings.app_version,
        python=platform.python_version(),
        uptime_seconds=int(time.time() - _STARTED_AT),
        scheduler_running=checkin_scheduler.running,
        next_run_at=checkin_scheduler.next_run_at(cfg.timezone),
        timezone=cfg.timezone,
        task_count=int(total),
        enabled_task_count=int(enabled),
        account_count=int(account_total),
        connected_account_count=len(telegram_manager.connected_ids()),
    )


@router.get("/version")
async def version():
    return {"name": settings.app_name, "version": settings.app_version}


@router.get("/time")
async def server_time():
    return {"now": datetime.now().isoformat(timespec="seconds")}
