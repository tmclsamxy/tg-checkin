"""Orchestrates task execution: persistence + notification."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import RunLog, Task
from .settings_store import RuntimeConfig, get_app_settings
from .telegram.executor import TaskError, execute_task
from .telegram.manager import telegram_manager

logger = logging.getLogger(__name__)

_run_lock = asyncio.Lock()


def _target_of(task: Task) -> str:
    return task.bot_username or task.group_id or "未知"


async def run_single_task(
    session: AsyncSession, task: Task, cfg, *, trigger: str = "manual"
) -> RunLog:
    """Execute one task, persist the run log and refresh the task summary fields."""
    started = time.perf_counter()
    reply: str | None = None
    error: str | None = None
    status = "success"

    try:
        client = await telegram_manager.ensure_client()
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)
        client = None

    if client is not None:
        result = await execute_task(client, task, RuntimeConfig(cfg))
        status = result.status
        reply = result.reply
        error = result.error
        if status == "success" and not reply:
            reply = "（无回复）"

    duration_ms = int((time.perf_counter() - started) * 1000)
    log = RunLog(
        task_id=task.id,
        task_name=task.name or _target_of(task),
        target=_target_of(task),
        status=status,
        reply=reply,
        error=error,
        duration_ms=duration_ms,
        trigger=trigger,
    )
    session.add(log)

    task.last_status = status
    task.last_message = (reply or error or "")[:2000] or None
    task.last_run_at = datetime.utcnow()
    await session.commit()
    await session.refresh(log)
    return log


async def run_task_by_id(task_id: int, *, trigger: str = "manual") -> RunLog:
    async with _run_lock:
        from .database import SessionLocal  # local import avoids a cycle at import time

        async with SessionLocal() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise ValueError("任务不存在")
            cfg = await get_app_settings(session)
            notify_enabled = cfg.notify_enabled
            notify_only_on_failure = cfg.notify_only_on_failure
            log = await run_single_task(session, task, cfg, trigger=trigger)
            await _notify([log], trigger, notify_enabled, notify_only_on_failure)
            return log


async def run_all_tasks(*, trigger: str = "manual", only_enabled: bool = True) -> list[RunLog]:
    """Run every (enabled) task in order. Safe against concurrent invocations."""
    if _run_lock.locked():
        logger.warning("已有签到任务正在执行，本次请求被忽略")
        return []

    async with _run_lock:
        from .database import SessionLocal

        logs: list[RunLog] = []
        interval = 0
        notify_enabled = False
        notify_only_on_failure = False

        async with SessionLocal() as session:
            cfg = await get_app_settings(session)
            interval = cfg.task_interval_seconds
            notify_enabled = cfg.notify_enabled
            notify_only_on_failure = cfg.notify_only_on_failure

            stmt = select(Task).order_by(Task.sort_order, Task.id)
            if only_enabled:
                stmt = stmt.where(Task.enabled.is_(True))
            tasks = (await session.execute(stmt)).scalars().all()

            if not tasks:
                logger.info("没有可执行的签到任务")
                return []

            for index, task in enumerate(tasks):
                logs.append(await run_single_task(session, task, cfg, trigger=trigger))
                if index < len(tasks) - 1 and interval:
                    await asyncio.sleep(interval)

        await _notify(logs, trigger, notify_enabled, notify_only_on_failure)
        return logs


def _build_summary(logs: list[RunLog], trigger: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success = sum(1 for log in logs if log.status == "success")
    failed = sum(1 for log in logs if log.status == "failed")
    label = "定时签到" if trigger == "scheduled" else "手动签到"

    lines = [f"📢 {label}报告 · {now}", f"共 {len(logs)} 项：✅ {success} ❌ {failed}", ""]
    for log in logs:
        icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(log.status, "•")
        name = log.task_name or log.target
        if log.status == "success":
            body = (log.reply or "无回复").strip().replace("\n", " ")
            lines.append(f"{icon} {name}：{body[:120]}")
        else:
            lines.append(f"{icon} {name}：{(log.error or '失败')[:120]}")
    return "\n".join(lines)


async def _notify(
    logs: list[RunLog], trigger: str, notify_enabled: bool, notify_only_on_failure: bool
) -> None:
    if not logs or not notify_enabled:
        return
    failed = [log for log in logs if log.status == "failed"]
    if notify_only_on_failure and not failed:
        return
    try:
        await telegram_manager.notify(_build_summary(logs, trigger))
    except Exception as exc:  # noqa: BLE001
        logger.warning("发送汇总通知失败: %s", exc)
