"""Application settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import Account, Task, User
from ..schemas import MessageResponse, SettingsOut, SettingsUpdate
from ..scheduler import checkin_scheduler
from ..settings_store import apply_settings_update, get_app_settings, to_settings_out
from ..telegram.manager import telegram_manager

router = APIRouter(prefix="/api/settings", tags=["settings"])


async def _counts(session: AsyncSession) -> dict[str, int]:
    account_count = await session.scalar(select(func.count(Account.id))) or 0
    task_count = await session.scalar(select(func.count(Task.id))) or 0
    return {
        "account_count": int(account_count),
        "task_count": int(task_count),
        "connected_account_count": len(telegram_manager.connected_ids()),
    }


@router.get("", response_model=SettingsOut)
async def read_settings(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    return to_settings_out(cfg, **await _counts(session))


@router.put("", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    apply_settings_update(cfg, payload)
    await session.commit()
    await session.refresh(cfg)

    checkin_scheduler.apply(
        enabled=cfg.schedule_enabled, schedule_time=cfg.schedule_time, timezone=cfg.timezone
    )
    return to_settings_out(cfg, **await _counts(session))


@router.post("/sync-scheduler", response_model=MessageResponse)
async def sync_scheduler(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    checkin_scheduler.apply(
        enabled=cfg.schedule_enabled, schedule_time=cfg.schedule_time, timezone=cfg.timezone
    )
    return MessageResponse(ok=True, message="调度已同步")


@router.post("/test-notification", response_model=MessageResponse)
async def test_notification(_: User = Depends(get_current_user)):
    delivered = await telegram_manager.test_notification()
    if not delivered:
        return MessageResponse(ok=False, message="通知发送失败，请检查通知配置")
    return MessageResponse(ok=True, message="测试通知已发送")
