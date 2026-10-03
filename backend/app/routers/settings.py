"""Application settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import User
from ..schemas import MessageResponse, SettingsOut, SettingsUpdate
from ..scheduler import checkin_scheduler
from ..settings_store import apply_settings_update, get_app_settings, to_settings_out
from ..telegram.manager import telegram_manager

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def read_settings(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    return to_settings_out(
        cfg, connected=telegram_manager.is_connected(), user=telegram_manager.user_label
    )


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
    return to_settings_out(
        cfg, connected=telegram_manager.is_connected(), user=telegram_manager.user_label
    )


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
