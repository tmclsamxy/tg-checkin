"""Telegram client lifecycle: login flow, session persistence, notifications."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from ..database import SessionLocal
from ..models import AppSetting
from ..security import decrypt_secret, encrypt_secret
from ..settings_store import get_app_settings

logger = logging.getLogger(__name__)


class TelegramManager:
    """Holds the user client (and optionally the notification bot client)."""

    def __init__(self) -> None:
        self._client: TelegramClient | None = None
        self._bot_client: TelegramClient | None = None
        self._lock = asyncio.Lock()
        self._pending: dict[str, Any] | None = None
        self._pending_state: str = "idle"  # idle | code | password
        self._user_label: str | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------------ #
    # status
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> str:
        return self._pending_state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def user_label(self) -> str | None:
        return self._user_label

    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected()

    # ------------------------------------------------------------------ #
    # login
    # ------------------------------------------------------------------ #
    async def request_code(self, api_id: str, api_hash: str, phone: str) -> None:
        async with self._lock:
            await self._close_pending()
            await self._disconnect()

            client = TelegramClient(StringSession(), int(api_id), api_hash)
            await client.connect()
            try:
                sent = await client.send_code_request(phone)
            except Exception:
                await client.disconnect()
                raise

            self._pending = {
                "client": client,
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "api_id": int(api_id),
                "api_hash": api_hash,
            }
            self._pending_state = "code"
            self._last_error = None
            logger.info("验证码已发送至 %s", phone)

    async def resend_code(self) -> None:
        async with self._lock:
            if not self._pending:
                raise RuntimeError("请先请求验证码")
            client = self._pending["client"]
            sent = await client.send_code_request(self._pending["phone"])
            self._pending["phone_code_hash"] = sent.phone_code_hash

    async def submit_code(self, code: str) -> None:
        async with self._lock:
            if not self._pending:
                raise RuntimeError("请先请求验证码")
            pending = self._pending
            client: TelegramClient = pending["client"]

            try:
                await client.sign_in(
                    pending["phone"], code.strip(), phone_code_hash=pending["phone_code_hash"]
                )
            except errors.SessionPasswordNeededError:
                self._pending_state = "password"
                return
            except errors.PhoneCodeInvalidError:
                raise ValueError("验证码错误，请重新输入") from None
            except errors.PhoneCodeExpiredError:
                self._pending_state = "idle"
                await self._close_pending()
                raise ValueError("验证码已过期，请重新请求") from None
            except errors.FloodWaitError as exc:
                raise ValueError(f"请求过于频繁，请 {exc.seconds} 秒后重试") from None

            await self._finish_login(pending)

    async def submit_password(self, password: str) -> None:
        async with self._lock:
            if not self._pending:
                raise RuntimeError("请先请求验证码")
            pending = self._pending
            client: TelegramClient = pending["client"]
            try:
                await client.sign_in(password=password)
            except errors.PasswordHashInvalidError:
                raise ValueError("两步验证密码错误") from None

            await self._finish_login(pending)

    async def cancel_login(self) -> None:
        async with self._lock:
            await self._close_pending()

    async def _finish_login(self, pending: dict[str, Any]) -> None:
        client: TelegramClient = pending["client"]
        try:
            session_str = client.session.save()
            async with SessionLocal() as session:
                cfg = await get_app_settings(session)
                cfg.api_id = str(pending["api_id"])
                cfg.api_hash_enc = encrypt_secret(pending["api_hash"])
                cfg.phone = pending["phone"]
                cfg.session_enc = encrypt_secret(session_str)
                await session.commit()

            me = await client.get_me()
            self._user_label = _display_name(me)
        except Exception:
            logger.exception("保存会话失败")
            await client.disconnect()
            raise

        self._client = client
        self._pending = None
        self._pending_state = "idle"
        self._last_error = None

    async def _close_pending(self) -> None:
        if self._pending:
            client = self._pending.get("client")
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # pragma: no cover
                    pass
        self._pending = None
        self._pending_state = "idle"

    # ------------------------------------------------------------------ #
    # client access
    # ------------------------------------------------------------------ #
    async def ensure_client(self) -> TelegramClient:
        """Return a connected, authorized client; restores the saved session if needed."""
        if self._client is not None and self._client.is_connected():
            if await self._client.is_user_authorized():
                return self._client
            await self._disconnect()

        async with SessionLocal() as session:
            cfg = await get_app_settings(session)
            api_id = cfg.api_id
            api_hash = decrypt_secret(cfg.api_hash_enc)
            session_str = decrypt_secret(cfg.session_enc)

        if not api_id or not api_hash:
            raise RuntimeError("尚未配置 Telegram API ID / API Hash")
        if not session_str:
            raise RuntimeError("尚未登录 Telegram，请先在「Telegram 账号」页面完成登录")

        client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError("Telegram 会话已失效，请重新登录")

        self._client = client
        try:
            me = await client.get_me()
            self._user_label = _display_name(me)
        except Exception:  # pragma: no cover - non fatal
            self._user_label = None
        self._last_error = None
        return client

    async def get_client(self) -> TelegramClient:
        return await self.ensure_client()

    async def disconnect(self) -> None:
        """Drop the current connection but keep the saved session."""
        await self.refresh_session()
        await self._disconnect()

    async def _disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # pragma: no cover
                pass
        self._client = None
        self._user_label = None

    async def logout(self) -> None:
        async with self._lock:
            await self._close_pending()
            if self._client is not None:
                try:
                    await self._client.log_out()
                except Exception:  # pragma: no cover
                    pass
            await self._disconnect()
            await self._close_bot()

            async with SessionLocal() as session:
                result = await session.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
                cfg = result.scalars().first()
                if cfg is not None:
                    cfg.session_enc = None
                    await session.commit()

    async def refresh_session(self) -> None:
        """Persist the (possibly rotated) session string back to the database."""
        if self._client is None or not self._client.is_connected():
            return
        try:
            session_str = self._client.session.save()
        except Exception:  # pragma: no cover
            return
        async with SessionLocal() as session:
            cfg = await get_app_settings(session)
            cfg.session_enc = encrypt_secret(session_str)
            await session.commit()

    # ------------------------------------------------------------------ #
    # notification
    # ------------------------------------------------------------------ #
    async def _close_bot(self) -> None:
        if self._bot_client is not None:
            try:
                await self._bot_client.disconnect()
            except Exception:  # pragma: no cover
                pass
            self._bot_client = None

    async def notify(self, text: str, *, force: bool = False) -> bool:
        """Send a notification. Returns True when delivered."""
        async with SessionLocal() as session:
            cfg = await get_app_settings(session)
            if not cfg.notify_enabled and not force:
                return False
            receiver = (cfg.notify_receiver_id or "").strip() or "me"
            bot_token = decrypt_secret(cfg.notify_bot_token_enc)
            api_id = cfg.api_id
            api_hash = decrypt_secret(cfg.api_hash_enc)

        try:
            if bot_token and api_id and api_hash:
                if self._bot_client is None or not self._bot_client.is_connected():
                    client = TelegramClient(StringSession(), int(api_id), api_hash)
                    await client.start(bot_token=bot_token)
                    self._bot_client = client
                await self._bot_client.send_message(_parse_peer(receiver), text)
                return True

            client = await self.ensure_client()
            await client.send_message(_parse_peer(receiver), text)
            return True
        except Exception as exc:
            logger.warning("发送通知失败: %s", exc)
            self._last_error = f"通知发送失败: {exc}"
            return False

    async def test_notification(self) -> bool:
        from datetime import datetime

        return await self.notify(
            f"✅ TG Checkin 通知测试\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            force=True,
        )


def _parse_peer(receiver: str):
    if receiver == "me":
        return "me"
    try:
        return int(receiver)
    except ValueError:
        return receiver


def _display_name(me) -> str:
    if me is None:
        return "未知"
    parts = [p for p in (getattr(me, "first_name", None), getattr(me, "last_name", None)) if p]
    name = " ".join(parts).strip()
    username = getattr(me, "username", None)
    if name and username:
        return f"{name} (@{username})"
    return name or (f"@{username}" if username else str(getattr(me, "id", "未知")))


telegram_manager = TelegramManager()
