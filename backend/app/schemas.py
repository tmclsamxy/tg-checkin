"""Pydantic request / response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

TargetType = Literal["bot", "group"]
ActionType = Literal["message", "button"]
ButtonType = Literal["text", "callback"]
RunStatus = Literal["success", "failed", "skipped"]


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    username: str
    must_change_password: bool


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
class SettingsOut(BaseModel):
    schedule_enabled: bool = True
    schedule_time: str = "08:00"
    timezone: str = "Asia/Shanghai"

    notify_enabled: bool = False
    notify_bot_token_masked: str | None = None
    has_notify_bot_token: bool = False
    notify_receiver_id: str | None = None
    notify_only_on_failure: bool = False
    notify_account_id: int | None = None

    reply_wait_seconds: int = 8
    start_command_delay: int = 5
    task_interval_seconds: int = 5
    max_retries: int = 1

    captcha_enabled: bool = True
    captcha_max_rounds: int = 2
    captcha_wait_seconds: int = 5

    account_count: int = 0
    connected_account_count: int = 0
    task_count: int = 0


class SettingsUpdate(BaseModel):
    schedule_enabled: bool | None = None
    schedule_time: str | None = None
    timezone: str | None = None

    notify_enabled: bool | None = None
    notify_bot_token: str | None = None
    notify_receiver_id: str | None = None
    notify_only_on_failure: bool | None = None
    notify_account_id: int | None = None

    reply_wait_seconds: int | None = Field(default=None, ge=1, le=120)
    start_command_delay: int | None = Field(default=None, ge=0, le=60)
    task_interval_seconds: int | None = Field(default=None, ge=0, le=300)
    max_retries: int | None = Field(default=None, ge=0, le=5)

    captcha_enabled: bool | None = None
    captcha_max_rounds: int | None = Field(default=None, ge=0, le=5)
    captcha_wait_seconds: int | None = Field(default=None, ge=1, le=60)

    @field_validator("schedule_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) != 5 or v[2] != ":" or not v.replace(":", "").isdigit():
            raise ValueError("schedule_time 必须是 HH:MM 格式")
        hour, minute = int(v[:2]), int(v[3:])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("schedule_time 超出合法范围")
        return v


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
class TaskBase(BaseModel):
    name: str = Field(default="", max_length=128)
    enabled: bool = True
    account_id: int | None = None
    target_type: TargetType = "bot"
    bot_username: str | None = None
    group_id: str | None = None
    action_type: ActionType = "message"
    message: str | None = None
    button_type: ButtonType | None = None
    button_text: str | None = None
    callback_data: str | None = None
    start_command: str | None = None
    auto_captcha: bool = True

    @field_validator("bot_username")
    @classmethod
    def _normalize_bot(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        return v if v.startswith("@") else f"@{v.lstrip('@')}"

    @field_validator("start_command")
    @classmethod
    def _normalize_cmd(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None

    @field_validator("group_id")
    @classmethod
    def _check_group(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(TaskBase):
    pass


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    sort_order: int
    account_id: int | None
    target_type: str
    bot_username: str | None
    group_id: str | None
    action_type: str
    message: str | None
    button_type: str | None
    button_text: str | None
    callback_data: str | None
    start_command: str | None
    auto_captcha: bool
    last_status: str | None
    last_message: str | None
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def target(self) -> str:
        return self.bot_username or self.group_id or "未知"


class TaskRunResult(BaseModel):
    task_id: int
    task_name: str
    status: RunStatus
    message: str | None = None
    error: str | None = None


# --------------------------------------------------------------------------- #
# Runs
# --------------------------------------------------------------------------- #
class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int | None
    account_id: int | None
    account_name: str
    task_name: str
    target: str
    status: str
    reply: str | None
    error: str | None
    duration_ms: int
    trigger: str
    created_at: datetime


class RunStats(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    today_total: int = 0
    today_success: int = 0
    today_failed: int = 0


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
class RequestCodeIn(BaseModel):
    """Blank fields reuse whatever is already stored on the account."""

    api_id: str | None = None
    api_hash: str | None = None
    phone: str | None = None


class VerifyCodeIn(BaseModel):
    code: str = Field(min_length=1)


class VerifyPasswordIn(BaseModel):
    password: str = Field(min_length=1)


# --------------------------------------------------------------------------- #
# Accounts
# --------------------------------------------------------------------------- #
class AccountCreate(BaseModel):
    name: str = Field(default="", max_length=128)
    api_id: str = Field(min_length=1)
    api_hash: str = Field(min_length=1)
    phone: str = Field(min_length=5)
    enabled: bool = True


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    api_id: str | None = None
    #: blank means "keep the stored hash"
    api_hash: str | None = None
    phone: str | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    sort_order: int
    api_id: str | None
    api_hash_masked: str | None = None
    has_api_hash: bool = False
    phone: str | None
    has_session: bool = False
    tg_user: str | None
    last_error: str | None
    last_connected_at: datetime | None

    # runtime, filled in by the router
    connected: bool = False
    needs_code: bool = False
    needs_password: bool = False
    task_count: int = 0

    created_at: datetime


class AccountReorder(BaseModel):
    ids: list[int]


class SystemInfo(BaseModel):
    version: str
    python: str
    uptime_seconds: int
    scheduler_running: bool
    next_run_at: datetime | None
    timezone: str
    task_count: int
    enabled_task_count: int
    account_count: int = 0
    connected_account_count: int = 0


class MessageResponse(BaseModel):
    ok: bool
    message: str
