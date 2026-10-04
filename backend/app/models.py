"""ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AppSetting(Base):
    """Single-row application configuration. Secrets are stored encrypted."""

    __tablename__ = "app_settings"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Legacy single-account credentials. Kept so upgrades can migrate them into
    # the first Account row; new code always reads credentials from `accounts`.
    api_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_hash_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_time: Mapped[str] = mapped_column(String(16), default="08:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")

    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_bot_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    notify_receiver_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notify_only_on_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    #: None means "use whichever account is connected"
    notify_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Behaviour tuning
    reply_wait_seconds: Mapped[int] = mapped_column(Integer, default=8)
    start_command_delay: Mapped[int] = mapped_column(Integer, default=5)
    task_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    max_retries: Mapped[int] = mapped_column(Integer, default=1)

    # Human-verification (captcha) auto answering
    captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_max_rounds: Mapped[int] = mapped_column(Integer, default=2)
    captcha_wait_seconds: Mapped[int] = mapped_column(Integer, default=5)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Account(Base):
    """One Telegram account: credentials, encrypted session and runtime status."""

    __tablename__ = "accounts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    api_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_hash_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Cached display name of the logged-in Telegram user
    tg_user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="account", lazy="noload")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    #: Owning Telegram account. NULL falls back to the first enabled account.
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )

    target_type: Mapped[str] = mapped_column(String(16), default="bot")  # bot | group
    bot_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action_type: Mapped[str] = mapped_column(String(16), default="message")  # message | button
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    button_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # text | callback
    button_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    callback_data: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_command: Mapped[str | None] = mapped_column(String(128), nullable=True)
    auto_captcha: Mapped[bool] = mapped_column(Boolean, default=True)

    last_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    runs: Mapped[list["RunLog"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="noload"
    )
    account: Mapped["Account | None"] = relationship(back_populates="tasks", lazy="noload")


class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    account_name: Mapped[str] = mapped_column(String(128), default="")
    task_name: Mapped[str] = mapped_column(String(128), default="")
    target: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="success")  # success | failed | skipped
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    trigger: Mapped[str] = mapped_column(String(16), default="manual")  # manual | scheduled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    task: Mapped["Task | None"] = relationship(back_populates="runs", lazy="noload")
