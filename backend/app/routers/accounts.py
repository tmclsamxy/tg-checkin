"""Telegram account management: CRUD plus a per-account login flow."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import Account, Task, User
from ..schemas import (
    AccountCreate,
    AccountOut,
    AccountReorder,
    AccountUpdate,
    MessageResponse,
    RequestCodeIn,
    VerifyCodeIn,
    VerifyPasswordIn,
)
from ..security import decrypt_secret, encrypt_secret, mask_secret
from ..telegram.manager import telegram_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _to_out(account: Account, task_count: int = 0) -> AccountOut:
    return AccountOut(
        id=account.id,
        name=account.name,
        enabled=account.enabled,
        sort_order=account.sort_order,
        api_id=account.api_id,
        api_hash_masked=mask_secret(decrypt_secret(account.api_hash_enc)),
        has_api_hash=bool(account.api_hash_enc),
        phone=account.phone,
        has_session=bool(account.session_enc),
        tg_user=account.tg_user or telegram_manager.user_label(account.id),
        last_error=account.last_error or telegram_manager.last_error(account.id),
        last_connected_at=account.last_connected_at,
        connected=telegram_manager.is_connected(account.id),
        needs_code=telegram_manager.state(account.id) == "code",
        needs_password=telegram_manager.state(account.id) == "password",
        task_count=task_count,
        created_at=account.created_at,
    )


async def _load(session: AsyncSession, account_id: int) -> Account:
    account = await session.get(Account, account_id)
    if account is None:
        raise HTTPException(404, "账号不存在")
    return account


async def _task_counts(session: AsyncSession) -> dict[int, int]:
    rows = await session.execute(
        select(Task.account_id, func.count(Task.id))
        .where(Task.account_id.is_not(None))
        .group_by(Task.account_id)
    )
    return {row[0]: row[1] for row in rows.fetchall()}


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[AccountOut])
async def list_accounts(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Account).order_by(Account.sort_order, Account.id)
    accounts = (await session.execute(stmt)).scalars().all()
    counts = await _task_counts(session)
    return [_to_out(account, counts.get(account.id, 0)) for account in accounts]


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(
    payload: AccountCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Register an account without logging in yet."""
    max_order = await session.scalar(select(func.coalesce(func.max(Account.sort_order), 0)))
    account = Account(
        name=(payload.name or "").strip() or payload.phone.strip(),
        enabled=payload.enabled,
        sort_order=int(max_order or 0) + 1,
        api_id=str(payload.api_id).strip(),
        api_hash_enc=encrypt_secret(payload.api_hash.strip()),
        phone=payload.phone.strip(),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return _to_out(account)


@router.put("/{account_id}", response_model=AccountOut)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("name") is not None:
        account.name = str(data["name"]).strip() or account.name
    if data.get("enabled") is not None:
        account.enabled = bool(data["enabled"])
    if data.get("api_id") is not None:
        account.api_id = str(data["api_id"]).strip() or account.api_id
    if data.get("phone") is not None:
        account.phone = str(data["phone"]).strip() or account.phone
    if data.get("api_hash"):
        account.api_hash_enc = encrypt_secret(str(data["api_hash"]).strip())

    account.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(account)

    if not account.enabled:
        # A disabled account must not keep a live connection around.
        await telegram_manager.disconnect(account_id)
    return _to_out(account)


@router.delete("/{account_id}", response_model=MessageResponse)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    if account.session_enc:
        await telegram_manager.logout(account_id)
    await telegram_manager.disconnect(account_id)
    telegram_manager.drop(account_id)

    task_count = await session.scalar(
        select(func.count(Task.id)).where(Task.account_id == account_id)
    )
    await session.delete(account)
    await session.commit()

    message = "账号已删除"
    if task_count:
        message = f"账号已删除，{task_count} 个关联任务改为使用默认账号"
    return MessageResponse(ok=True, message=message)


@router.post("/reorder", response_model=MessageResponse)
async def reorder_accounts(
    payload: AccountReorder,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    for index, account_id in enumerate(payload.ids):
        account = await session.get(Account, int(account_id))
        if account is not None:
            account.sort_order = index
    await session.commit()
    return MessageResponse(ok=True, message="顺序已保存")


# --------------------------------------------------------------------------- #
# login flow
# --------------------------------------------------------------------------- #
@router.post("/{account_id}/request-code", response_model=AccountOut)
async def request_code(
    account_id: int,
    payload: RequestCodeIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)

    api_id = (payload.api_id or "").strip() or (account.api_id or "")
    api_hash = (payload.api_hash or "").strip() or decrypt_secret(account.api_hash_enc) or ""
    phone = (payload.phone or "").strip() or (account.phone or "")

    if not api_id or not api_hash:
        raise HTTPException(400, "请先填写 API ID 与 API Hash")
    if not phone:
        raise HTTPException(400, "请先填写手机号")

    # only overwrite what the caller actually supplied, so re-login keeps the hash
    if (payload.api_id or "").strip():
        account.api_id = api_id
    if (payload.api_hash or "").strip():
        account.api_hash_enc = encrypt_secret(api_hash)
    if (payload.phone or "").strip():
        account.phone = phone
    await session.commit()
    await session.refresh(account)

    try:
        await telegram_manager.request_code(account_id, api_id, api_hash, phone)
    except Exception as exc:  # noqa: BLE001
        logger.warning("账号 %s 请求验证码失败: %s", account_id, exc)
        raise HTTPException(400, f"请求验证码失败：{exc}") from exc
    return _to_out(account)


@router.post("/{account_id}/resend-code", response_model=AccountOut)
async def resend_code(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    try:
        await telegram_manager.resend_code(account_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"重发验证码失败：{exc}") from exc
    return _to_out(account)


@router.post("/{account_id}/verify-code", response_model=AccountOut)
async def verify_code(
    account_id: int,
    payload: VerifyCodeIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    try:
        await telegram_manager.submit_code(account_id, payload.code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"登录失败：{exc}") from exc
    await session.refresh(account)
    return _to_out(account)


@router.post("/{account_id}/verify-password", response_model=AccountOut)
async def verify_password(
    account_id: int,
    payload: VerifyPasswordIn,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    try:
        await telegram_manager.submit_password(account_id, payload.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"登录失败：{exc}") from exc
    await session.refresh(account)
    return _to_out(account)


@router.post("/{account_id}/cancel-login", response_model=AccountOut)
async def cancel_login(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    await telegram_manager.cancel_login(account_id)
    return _to_out(account)


# --------------------------------------------------------------------------- #
# connection
# --------------------------------------------------------------------------- #
@router.post("/{account_id}/connect", response_model=AccountOut)
async def connect(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Restore a previously saved session."""
    account = await _load(session, account_id)
    try:
        await telegram_manager.ensure_client(account_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    await session.refresh(account)
    return _to_out(account)


@router.post("/{account_id}/disconnect", response_model=AccountOut)
async def disconnect(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    await telegram_manager.disconnect(account_id)
    return _to_out(account)


@router.post("/{account_id}/logout", response_model=AccountOut)
async def logout(
    account_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    account = await _load(session, account_id)
    await telegram_manager.logout(account_id)
    await session.refresh(account)
    return _to_out(account)


@router.post("/connect-all", response_model=MessageResponse)
async def connect_all(_: User = Depends(get_current_user)):
    await telegram_manager.restore_all()
    connected = telegram_manager.connected_ids()
    return MessageResponse(ok=True, message=f"已连接 {len(connected)} 个账号")
