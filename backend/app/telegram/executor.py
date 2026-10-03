"""Check-in task execution engine (pure logic, given a connected Telethon client)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from telethon import errors

from ..models import Task
from ..settings_store import RuntimeConfig

logger = logging.getLogger(__name__)

MAX_SCAN_MESSAGES = 12
MAX_REPLY_MESSAGES = 5


class TaskError(Exception):
    """Raised when a task cannot be completed."""


class NotConfiguredError(TaskError):
    pass


class NotAuthorizedError(TaskError):
    pass


class FloodWaitError(TaskError):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"Telegram 限制：需等待 {seconds} 秒")
        self.seconds = seconds


@dataclass
class TaskResult:
    status: str  # success | failed | skipped
    reply: str | None = None
    error: str | None = None
    duration_ms: int = 0
    target: str = ""
    attempts: int = 1
    detail: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _extract_text(message) -> str:
    """Best-effort plain-text rendering of a Telegram message."""
    if message is None:
        return ""
    text = getattr(message, "message", None)
    if text:
        return str(text).strip()

    action = getattr(message, "action", None)
    if action is not None:
        for attr in ("message", "title"):
            value = getattr(action, attr, None)
            if value:
                return str(value).strip()
        return str(action)

    if getattr(message, "media", None) is not None:
        return "[媒体消息]"
    return ""


async def _resolve_entity(client, task: Task):
    if task.target_type == "bot":
        if not task.bot_username:
            raise TaskError("未配置机器人用户名")
        return await client.get_entity(task.bot_username)

    if not task.group_id:
        raise TaskError("未配置群组 ID")
    raw = str(task.group_id).strip()
    if raw.startswith("@"):
        return await client.get_entity(raw)
    try:
        return await client.get_entity(int(raw))
    except ValueError as exc:
        raise TaskError(f"群组 ID 无效: {raw}") from exc


async def _latest_message_id(client, entity) -> int:
    try:
        messages = await client.get_messages(entity, limit=1)
    except Exception:  # pragma: no cover - defensive
        return 0
    return messages[0].id if messages else 0


def _button_callback_data(button) -> bytes | None:
    """Read a button's callback payload across Telethon versions.

    Telethon <= 1.44 exposes ``KeyboardButtonCallback.data`` directly, while
    newer releases moved the payload into ``button.type.data``.
    """
    for holder in (button, getattr(button, "type", None)):
        data = getattr(holder, "data", None)
        if isinstance(data, bytes):
            return data
        if isinstance(data, str):
            return data.encode("utf-8")
    return None


def _iter_buttons(message):
    markup = getattr(message, "reply_markup", None)
    if not markup:
        return
    for row in getattr(markup, "rows", None) or []:
        for button in getattr(row, "buttons", None) or []:
            yield button


async def _find_button_message(client, entity, task: Task):
    """Scan recent messages for one containing the requested button.

    Returns ``(message, click_kwargs)`` where ``click_kwargs`` can be passed
    straight to :meth:`telethon.tl.custom.Message.click`.
    """
    async for message in client.iter_messages(entity, limit=MAX_SCAN_MESSAGES):
        for button in _iter_buttons(message):
            text = getattr(button, "text", None)
            if task.button_type == "text":
                if text == task.button_text:
                    return message, {"text": text}
            else:
                data = _button_callback_data(button)
                if data is not None and data.decode("utf-8", "ignore") == task.callback_data:
                    return message, {"data": data}
    return None, None


async def _collect_replies(client, entity, baseline_id: int, *, with_sender: bool) -> str:
    """Collect messages newer than `baseline_id`, oldest first."""
    collected: list[str] = []
    async for message in client.iter_messages(entity, min_id=baseline_id, limit=MAX_REPLY_MESSAGES):
        if message.id == baseline_id:
            continue
        text = _extract_text(message)
        if not text:
            continue
        if with_sender:
            try:
                sender = await message.get_sender()
            except Exception:  # pragma: no cover - defensive
                sender = None
            if sender is not None:
                name = getattr(sender, "username", None) or (
                    " ".join(
                        p for p in (getattr(sender, "first_name", None), getattr(sender, "last_name", None)) if p
                    ).strip()
                )
                collected.append(f"{name or sender.id}: {text}")
                continue
        collected.append(text)

    collected.reverse()
    return "\n".join(collected)


# --------------------------------------------------------------------------- #
# main entry point
# --------------------------------------------------------------------------- #
async def execute_task(client, task: Task, cfg: RuntimeConfig) -> TaskResult:
    """Execute a single check-in task and return its outcome."""
    started = time.perf_counter()
    target = task.bot_username or task.group_id or "未知"

    # max_retries=0 -> a single attempt, max_retries=2 -> up to three attempts
    attempts = 1 + max(0, int(cfg.max_retries or 0))
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            reply = await _execute_once(client, task, cfg)
            return TaskResult(
                status="success",
                reply=reply or None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                target=target,
                attempts=attempt,
            )
        except errors.FloodWaitError as exc:
            wait_seconds = int(getattr(exc, "seconds", 30) or 30)
            last_error = f"触发 Telegram 频率限制，需等待 {wait_seconds} 秒"
            logger.warning("任务 %s 触发 FloodWait: %s", task.id, wait_seconds)
            # Waiting longer than two minutes is not worth blocking the whole run.
            if wait_seconds <= 120 and attempt < attempts:
                await asyncio.sleep(wait_seconds + 1)
                continue
        except asyncio.TimeoutError:
            last_error = "操作超时"
            logger.warning("任务 %s 超时（第 %s 次）", task.id, attempt)
        except Exception as exc:  # noqa: BLE001 - surface any Telegram error to the UI
            last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("任务 %s 执行失败（第 %s 次）", task.id, attempt)
            if attempt < attempts:
                await asyncio.sleep(3 * attempt)
                continue

    return TaskResult(
        status="failed",
        error=last_error or "未知错误",
        duration_ms=int((time.perf_counter() - started) * 1000),
        target=target,
    )


async def _execute_once(client, task: Task, cfg: RuntimeConfig) -> str:
    entity = await _resolve_entity(client, task)

    if task.start_command:
        await client.send_message(entity, task.start_command)
        await asyncio.sleep(max(0, cfg.start_command_delay))

    baseline = await _latest_message_id(client, entity)

    if task.action_type == "message":
        if not task.message:
            raise TaskError("未配置消息内容")
        await client.send_message(entity, task.message)

    elif task.action_type == "button":
        message, click_kwargs = await _find_button_message(client, entity, task)
        if message is None:
            label = task.button_text if task.button_type == "text" else task.callback_data
            raise TaskError(f"未找到按钮：{label}")
        await message.click(**click_kwargs)
    else:
        raise TaskError(f"不支持的任务类型：{task.action_type}")

    await asyncio.sleep(max(1, cfg.reply_wait_seconds))
    return await _collect_replies(client, entity, baseline, with_sender=task.target_type == "group")
