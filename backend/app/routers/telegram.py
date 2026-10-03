"""Telegram account endpoints: login flow and connection status."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import User
from ..schemas import (
    MessageResponse,
    RequestCodeIn,
    TelegramStatus,
    VerifyCodeIn,
    VerifyPasswordIn,
)
from ..settings_store import get_app_settings
from ..telegram.manager import telegram_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


def _status(phone: str | None = None) -> TelegramStatus:
    return TelegramStatus(
        configured=bool(phone),
        connected=telegram_manager.is_connected(),
        needs_code=telegram_manager.state == "code",
        needs_password=telegram_manager.state == "password",
        user=telegram_manager.user_label,
        phone=phone,
        detail=telegram_manager.last_error,
    )


@router.get("/status", response_model=TelegramStatus)
async def status(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    return _status(cfg.phone)


@router.post("/request-code", response_model=TelegramStatus)
async def request_code(
    payload: RequestCodeIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Persist the API credentials and ask Telegram for a login code."""
    cfg = await get_app_settings(session)
    cfg.phone = payload.phone
    cfg.api_id = str(payload.api_id).strip()
    from ..security import encrypt_secret

    cfg.api_hash_enc = encrypt_secret(payload.api_hash.strip())
    await session.commit()

    try:
        await telegram_manager.request_code(cfg.api_id, payload.api_hash.strip(), payload.phone)
    except Exception as exc:  # noqa: BLE001
        logger.warning("请求验证码失败: %s", exc)
        raise HTTPException(400, f"请求验证码失败：{exc}") from exc

    return _status(cfg.phone)


@router.post("/resend-code", response_model=TelegramStatus)
async def resend_code(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    try:
        await telegram_manager.resend_code()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"重发验证码失败：{exc}") from exc
    return _status(cfg.phone)


@router.post("/verify-code", response_model=TelegramStatus)
async def verify_code(
    payload: VerifyCodeIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    try:
        await telegram_manager.submit_code(payload.code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"登录失败：{exc}") from exc
    return _status(cfg.phone)


@router.post("/verify-password", response_model=TelegramStatus)
async def verify_password(
    payload: VerifyPasswordIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    try:
        await telegram_manager.submit_password(payload.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"登录失败：{exc}") from exc
    return _status(cfg.phone)


@router.post("/cancel-login", response_model=TelegramStatus)
async def cancel_login(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    await telegram_manager.cancel_login()
    return _status(cfg.phone)


@router.post("/connect", response_model=TelegramStatus)
async def connect(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Restore a previously saved session."""
    cfg = await get_app_settings(session)
    try:
        await telegram_manager.ensure_client()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return _status(cfg.phone)


@router.post("/disconnect", response_model=TelegramStatus)
async def disconnect(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cfg = await get_app_settings(session)
    await telegram_manager.disconnect()
    return _status(cfg.phone)


@router.post("/logout", response_model=MessageResponse)
async def logout(_: User = Depends(get_current_user)):
    await telegram_manager.logout()
    return MessageResponse(ok=True, message="已退出登录并清除会话")


@router.post("/test-notification", response_model=MessageResponse)
async def test_notification(_: User = Depends(get_current_user)):
    delivered = await telegram_manager.test_notification()
    if not delivered:
        return MessageResponse(ok=False, message="通知发送失败，请检查通知配置")
    return MessageResponse(ok=True, message="测试通知已发送")
