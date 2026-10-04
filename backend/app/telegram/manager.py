"""Telegram client lifecycle for multiple accounts.

Each :class:`Account` row owns its own ``TelegramClient`` and its own login
state machine, so several accounts can be signed in at the same time and run
their own tasks. Runtime state lives in :class:`AccountSession`; everything is
kept in memory and rebuilt from the encrypted session string on restart.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

from ..database import SessionLocal
from ..models import Account
from ..security import decrypt_secret, encrypt_secret
from ..settings_store import get_app_settings

logger = logging.getLogger(__name__)


@dataclass
class AccountSession:
    """In-memory runtime state for a single Telegram account."""

    account_id: int
    client: TelegramClient | None = None
    authorized: bool = False
    pending: dict[str, Any] | None = None
    state: str = "idle"  # idle | code | password
    user_label: str | None = None
    last_error: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected()


class TelegramManager:
    """Session pool keyed by account id."""

    def __init__(self) -> None:
        self._sessions: dict[int, AccountSession] = {}
        self._bot_client: TelegramClient | None = None
        self._bot_owner: int | None = None

    # ------------------------------------------------------------------ #
    # session registry
    # ------------------------------------------------------------------ #
    def session(self, account_id: int | None) -> AccountSession | None:
        if account_id is None:
            return None
        return self._sessions.get(account_id)

    def _session_for(self, account_id: int) -> AccountSession:
        session = self._sessions.get(account_id)
        if session is None:
            session = AccountSession(account_id=account_id)
            self._sessions[account_id] = session
        return session

    def drop(self, account_id: int) -> None:
        self._sessions.pop(account_id, None)

    # ------------------------------------------------------------------ #
    # status helpers
    # ------------------------------------------------------------------ #
    def state(self, account_id: int | None) -> str:
        session = self.session(account_id)
        return session.state if session else "idle"

    def user_label(self, account_id: int | None) -> str | None:
        session = self.session(account_id)
        return session.user_label if session else None

    def last_error(self, account_id: int | None) -> str | None:
        session = self.session(account_id)
        return session.last_error if session else None

    def is_connected(self, account_id: int | None = None) -> bool:
        if account_id is not None:
            session = self.session(account_id)
            return bool(session and session.is_connected())
        return any(item.is_connected() for item in self._sessions.values())

    def connected_ids(self) -> list[int]:
        return [item.account_id for item in self._sessions.values() if item.is_connected()]

    # ------------------------------------------------------------------ #
    # account lookup
    # ------------------------------------------------------------------ #
    async def _get_account(self, account_id: int) -> Account | None:
        async with SessionLocal() as session:
            return await session.get(Account, account_id)

    # ------------------------------------------------------------------ #
    # login flow
    # ------------------------------------------------------------------ #
    async def request_code(
        self, account_id: int, api_id: str, api_hash: str, phone: str
    ) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            await self._close_pending(session)
            await self._disconnect_session(session)

            client = TelegramClient(StringSession(), int(api_id), api_hash)
            await client.connect()
            try:
                sent = await client.send_code_request(phone)
            except Exception:
                await client.disconnect()
                session.last_error = "请求验证码失败"
                raise

            session.pending = {
                "client": client,
                "phone": phone,
                "phone_code_hash": sent.phone_code_hash,
                "api_id": int(api_id),
                "api_hash": api_hash,
            }
            session.state = "code"
            session.last_error = None
            logger.info("账号 %s 的验证码已发送至 %s", account_id, phone)

    async def resend_code(self, account_id: int) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            if not session.pending:
                raise RuntimeError("请先请求验证码")
            client = session.pending["client"]
            sent = await client.send_code_request(session.pending["phone"])
            session.pending["phone_code_hash"] = sent.phone_code_hash

    async def submit_code(self, account_id: int, code: str) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            if not session.pending:
                raise RuntimeError("请先请求验证码")
            pending = session.pending
            client: TelegramClient = pending["client"]

            try:
                await client.sign_in(
                    pending["phone"], code.strip(), phone_code_hash=pending["phone_code_hash"]
                )
            except errors.SessionPasswordNeededError:
                session.state = "password"
                return
            except errors.PhoneCodeInvalidError:
                raise ValueError("验证码错误，请重新输入") from None
            except errors.PhoneCodeExpiredError:
                session.state = "idle"
                await self._close_pending(session)
                raise ValueError("验证码已过期，请重新请求") from None
            except errors.FloodWaitError as exc:
                raise ValueError(f"请求过于频繁，请 {exc.seconds} 秒后重试") from None

            await self._finish_login(session, pending)

    async def submit_password(self, account_id: int, password: str) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            if not session.pending:
                raise RuntimeError("请先请求验证码")
            pending = session.pending
            client: TelegramClient = pending["client"]
            try:
                await client.sign_in(password=password)
            except errors.PasswordHashInvalidError:
                raise ValueError("两步验证密码错误") from None

            await self._finish_login(session, pending)

    async def cancel_login(self, account_id: int) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            await self._close_pending(session)

    async def _finish_login(self, session: AccountSession, pending: dict[str, Any]) -> None:
        client: TelegramClient = pending["client"]
        me = await client.get_me()
        label = _display_name(me)

        try:
            session_str = client.session.save()
            async with SessionLocal() as db:
                account = await db.get(Account, session.account_id)
                if account is None:
                    raise RuntimeError("账号不存在")
                account.api_id = str(pending["api_id"])
                account.api_hash_enc = encrypt_secret(pending["api_hash"])
                account.phone = pending["phone"]
                account.session_enc = encrypt_secret(session_str)
                account.tg_user = label
                account.last_error = None
                account.last_connected_at = datetime.utcnow()
                if not (account.name or "").strip():
                    account.name = label
                await db.commit()
        except Exception:
            logger.exception("保存账号 %s 的会话失败", session.account_id)
            await client.disconnect()
            session.last_error = "保存会话失败"
            raise

        session.client = client
        session.authorized = True
        session.pending = None
        session.state = "idle"
        session.last_error = None
        session.user_label = label

    async def _close_pending(self, session: AccountSession) -> None:
        if session.pending:
            client = session.pending.get("client")
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # pragma: no cover
                    pass
        session.pending = None
        session.state = "idle"

    # ------------------------------------------------------------------ #
    # client access
    # ------------------------------------------------------------------ #
    async def ensure_client(self, account_id: int | None = None) -> TelegramClient:
        """Return a connected, authorized client for an account.

        ``account_id=None`` picks the first enabled account that has a session.
        """
        if account_id is None:
            account_id = await self._default_account_id()
        if account_id is None:
            raise RuntimeError("尚未添加 Telegram 账号，请先在「Telegram 账号」页面添加并登录")

        account = await self._get_account(account_id)
        if account is None:
            self.drop(account_id)
            raise RuntimeError("该任务所属的 Telegram 账号已被删除")

        session = self._session_for(account_id)
        async with session.lock:
            if session.is_connected() and session.authorized:
                return session.client  # type: ignore[return-value]

            if session.is_connected():
                try:
                    if await session.client.is_user_authorized():  # type: ignore[union-attr]
                        session.authorized = True
                        return session.client  # type: ignore[return-value]
                except Exception:  # pragma: no cover - transient
                    pass
                await self._disconnect_session(session)

            api_id = account.api_id
            api_hash = decrypt_secret(account.api_hash_enc)
            session_str = decrypt_secret(account.session_enc)

            if not api_id or not api_hash:
                raise RuntimeError(f"账号「{account.name}」尚未填写 API ID / API Hash")
            if not session_str:
                raise RuntimeError(f"账号「{account.name}」尚未登录，请先完成登录")

            client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                await self._record_error(account_id, "Telegram 会话已失效，请重新登录")
                raise RuntimeError(f"账号「{account.name}」的会话已失效，请重新登录")

            session.client = client
            session.authorized = True
            session.last_error = None
            try:
                me = await client.get_me()
                session.user_label = _display_name(me)
                await self._touch(account_id, session.user_label)
            except Exception:  # pragma: no cover - non fatal
                pass
            return client

    async def _default_account_id(self) -> int | None:
        async with SessionLocal() as db:
            stmt = (
                select(Account)
                .where(Account.enabled.is_(True), Account.session_enc.is_not(None))
                .order_by(Account.sort_order, Account.id)
                .limit(1)
            )
            account = (await db.execute(stmt)).scalars().first()
            if account is not None:
                return account.id
            # No usable session yet — fall back to any enabled account so the
            # error message can explain what is missing.
            stmt = (
                select(Account)
                .where(Account.enabled.is_(True))
                .order_by(Account.sort_order, Account.id)
                .limit(1)
            )
            account = (await db.execute(stmt)).scalars().first()
            return account.id if account else None

    async def _record_error(self, account_id: int, message: str) -> None:
        session = self._session_for(account_id)
        session.last_error = message
        session.authorized = False
        async with SessionLocal() as db:
            account = await db.get(Account, account_id)
            if account is not None:
                account.last_error = message
                await db.commit()

    async def _touch(self, account_id: int, label: str | None) -> None:
        async with SessionLocal() as db:
            account = await db.get(Account, account_id)
            if account is not None:
                account.tg_user = label or account.tg_user
                account.last_error = None
                account.last_connected_at = datetime.utcnow()
                await db.commit()

    # ------------------------------------------------------------------ #
    # disconnect / logout
    # ------------------------------------------------------------------ #
    async def disconnect(self, account_id: int | None = None) -> None:
        """Drop connections but keep the saved sessions."""
        await self.refresh_session(account_id)
        targets = [account_id] if account_id is not None else list(self._sessions)
        for target in targets:
            session = self._sessions.get(target)
            if session is not None:
                await self._disconnect_session(session)

    async def _disconnect_session(self, session: AccountSession) -> None:
        if session.client is not None:
            try:
                await session.client.disconnect()
            except Exception:  # pragma: no cover
                pass
        session.client = None
        session.authorized = False
        session.user_label = None
        if self._bot_owner == session.account_id:
            await self._close_bot()

    async def logout(self, account_id: int) -> None:
        session = self._session_for(account_id)
        async with session.lock:
            await self._close_pending(session)
            if session.client is not None:
                try:
                    await session.client.log_out()
                except Exception:  # pragma: no cover
                    pass
            await self._disconnect_session(session)

            async with SessionLocal() as db:
                account = await db.get(Account, account_id)
                if account is not None:
                    account.session_enc = None
                    account.tg_user = None
                    account.last_error = None
                    await db.commit()

    async def refresh_session(self, account_id: int | None = None) -> None:
        """Persist rotated session strings back to the database."""
        targets = [account_id] if account_id is not None else list(self._sessions)
        for target in targets:
            session = self._sessions.get(target)
            if session is None or not session.is_connected():
                continue
            try:
                session_str = session.client.session.save()  # type: ignore[union-attr]
            except Exception:  # pragma: no cover
                continue
            async with SessionLocal() as db:
                account = await db.get(Account, target)
                if account is not None:
                    account.session_enc = encrypt_secret(session_str)
                    await db.commit()

    async def restore_all(self) -> None:
        """Best-effort reconnect of every enabled account that has a session."""
        async with SessionLocal() as db:
            stmt = (
                select(Account)
                .where(Account.enabled.is_(True), Account.session_enc.is_not(None))
                .order_by(Account.sort_order, Account.id)
            )
            accounts = (await db.execute(stmt)).scalars().all()
            ids = [account.id for account in accounts]

        for account_id in ids:
            try:
                await self.ensure_client(account_id)
                logger.info("账号 %s 会话已恢复：%s", account_id, self.user_label(account_id))
            except Exception as exc:  # noqa: BLE001
                logger.info("账号 %s 未自动连接（%s）", account_id, exc)

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
            self._bot_owner = None

    async def notify(self, text: str, *, force: bool = False) -> bool:
        """Send a notification. Returns True when delivered."""
        async with SessionLocal() as db:
            cfg = await get_app_settings(db)
            if not cfg.notify_enabled and not force:
                return False
            receiver = (cfg.notify_receiver_id or "").strip() or "me"
            bot_token = decrypt_secret(cfg.notify_bot_token_enc)
            preferred_id = cfg.notify_account_id

        try:
            if bot_token:
                api_id, api_hash, owner = await self._bot_credentials(preferred_id)
                if api_id and api_hash:
                    if (
                        self._bot_client is None
                        or not self._bot_client.is_connected()
                        or self._bot_owner != owner
                    ):
                        await self._close_bot()
                        client = TelegramClient(StringSession(), int(api_id), api_hash)
                        await client.start(bot_token=bot_token)
                        self._bot_client = client
                        self._bot_owner = owner
                    await self._bot_client.send_message(_parse_peer(receiver), text)
                    return True

            client = await self._notification_client(preferred_id)
            await client.send_message(_parse_peer(receiver), text)
            return True
        except Exception as exc:
            logger.warning("发送通知失败: %s", exc)
            return False

    async def _bot_credentials(self, preferred_id: int | None) -> tuple[str | None, str | None, int | None]:
        """Any account's api_id/api_hash can host the notification bot client."""
        if preferred_id is not None:
            account = await self._get_account(preferred_id)
            if account is not None and account.api_id:
                return account.api_id, decrypt_secret(account.api_hash_enc), account.id
        async with SessionLocal() as db:
            account = (
                await db.execute(select(Account).order_by(Account.sort_order, Account.id).limit(1))
            ).scalars().first()
        if account is None or not account.api_id:
            return None, None, None
        return account.api_id, decrypt_secret(account.api_hash_enc), account.id

    async def _notification_client(self, preferred_id: int | None) -> TelegramClient:
        """A connected user client used to deliver notifications."""
        if preferred_id is not None:
            return await self.ensure_client(preferred_id)
        for account_id in self.connected_ids():
            client = await self.ensure_client(account_id)
            return client
        return await self.ensure_client(None)

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


__all__ = ["AccountSession", "TelegramManager", "telegram_manager"]
