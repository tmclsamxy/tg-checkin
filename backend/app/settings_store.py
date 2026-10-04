"""Read/write the single-row application configuration."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AppSetting
from .schemas import SettingsOut, SettingsUpdate
from .security import decrypt_secret, encrypt_secret, mask_secret


async def get_app_settings(session: AsyncSession) -> AppSetting:
    """Return the settings row, creating it on first use."""
    result = await session.execute(select(AppSetting).order_by(AppSetting.id).limit(1))
    cfg = result.scalars().first()
    if cfg is None:
        cfg = AppSetting()
        session.add(cfg)
        await session.commit()
        await session.refresh(cfg)
    return cfg


def to_settings_out(cfg: AppSetting, *, connected: bool = False, user: str | None = None) -> SettingsOut:
    api_hash = decrypt_secret(cfg.api_hash_enc)
    bot_token = decrypt_secret(cfg.notify_bot_token_enc)
    return SettingsOut(
        api_id=cfg.api_id,
        api_hash_masked=mask_secret(api_hash),
        has_api_hash=bool(api_hash),
        phone=cfg.phone,
        schedule_enabled=cfg.schedule_enabled,
        schedule_time=cfg.schedule_time,
        timezone=cfg.timezone,
        notify_enabled=cfg.notify_enabled,
        notify_bot_token_masked=mask_secret(bot_token),
        has_notify_bot_token=bool(bot_token),
        notify_receiver_id=cfg.notify_receiver_id,
        notify_only_on_failure=cfg.notify_only_on_failure,
        reply_wait_seconds=cfg.reply_wait_seconds,
        start_command_delay=cfg.start_command_delay,
        task_interval_seconds=cfg.task_interval_seconds,
        max_retries=cfg.max_retries,
        captcha_enabled=cfg.captcha_enabled,
        captcha_max_rounds=cfg.captcha_max_rounds,
        captcha_wait_seconds=cfg.captcha_wait_seconds,
        telegram_connected=connected,
        telegram_user=user,
        has_session=bool(cfg.session_enc),
    )


def apply_settings_update(cfg: AppSetting, payload: SettingsUpdate) -> None:
    """Apply a partial update. Empty secrets are ignored so the UI can leave them blank."""
    data = payload.model_dump(exclude_unset=True)

    if "api_id" in data and data["api_id"] is not None:
        cfg.api_id = str(data["api_id"]).strip() or None
    if "phone" in data and data["phone"] is not None:
        cfg.phone = str(data["phone"]).strip() or None
    if "api_hash" in data:
        value = (data["api_hash"] or "").strip()
        if value:
            cfg.api_hash_enc = encrypt_secret(value)

    for field in ("schedule_enabled", "notify_enabled", "notify_only_on_failure", "captcha_enabled"):
        if data.get(field) is not None:
            setattr(cfg, field, bool(data[field]))

    for field in ("schedule_time", "timezone", "notify_receiver_id"):
        if data.get(field) is not None:
            setattr(cfg, field, str(data[field]).strip())

    for field in (
        "reply_wait_seconds",
        "start_command_delay",
        "task_interval_seconds",
        "max_retries",
        "captcha_max_rounds",
        "captcha_wait_seconds",
    ):
        if data.get(field) is not None:
            setattr(cfg, field, int(data[field]))

    if "notify_bot_token" in data:
        value = (data["notify_bot_token"] or "").strip()
        if value:
            cfg.notify_bot_token_enc = encrypt_secret(value)


class RuntimeConfig:
    """Plain snapshot of the settings needed to execute tasks."""

    __slots__ = (
        "reply_wait_seconds",
        "start_command_delay",
        "task_interval_seconds",
        "max_retries",
        "captcha_enabled",
        "captcha_max_rounds",
        "captcha_wait_seconds",
    )

    def __init__(self, cfg: AppSetting) -> None:
        self.reply_wait_seconds = cfg.reply_wait_seconds
        self.start_command_delay = cfg.start_command_delay
        self.task_interval_seconds = cfg.task_interval_seconds
        self.max_retries = cfg.max_retries
        self.captcha_enabled = cfg.captcha_enabled
        self.captcha_max_rounds = cfg.captcha_max_rounds
        self.captcha_wait_seconds = cfg.captcha_wait_seconds
