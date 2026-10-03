"""Daily check-in scheduler (APScheduler)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .runner import run_all_tasks

logger = logging.getLogger(__name__)

JOB_ID = "daily_checkin"


def _safe_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - unknown tz key
        logger.warning("未知时区 %s，回退到 UTC", name)
        return ZoneInfo("UTC")


class CheckinScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
        self._started = False

    @property
    def running(self) -> bool:
        return self._started and self._scheduler.running

    def start(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("调度器已启动")

    def shutdown(self) -> None:
        if self._started and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._started = False

    def apply(self, *, enabled: bool, schedule_time: str, timezone: str) -> None:
        """Create or update the cron job."""
        if not self._started:
            self.start()

        if self._scheduler.get_job(JOB_ID) is not None:
            self._scheduler.remove_job(JOB_ID)

        if not enabled:
            logger.info("定时签到已关闭")
            return

        try:
            hour, minute = (int(part) for part in str(schedule_time).split(":"))
        except (ValueError, AttributeError):
            logger.warning("签到时间 %s 无效，使用默认 08:00", schedule_time)
            hour, minute = 8, 0

        trigger = CronTrigger(hour=hour, minute=minute, timezone=_safe_zone(timezone))
        self._scheduler.add_job(
            self._job,
            trigger=trigger,
            id=JOB_ID,
            name="每日签到",
            replace_existing=True,
            misfire_grace_time=300,
            max_instances=1,
            coalesce=True,
        )
        logger.info("已设置每日 %02d:%02d (%s) 执行签到", hour, minute, timezone)

    def next_run_at(self, timezone: str) -> datetime | None:
        job = self._scheduler.get_job(JOB_ID)
        if job is None:
            return None
        # APScheduler renamed the attribute in 3.x/4.x; support both.
        next_time = getattr(job, "next_run_time", None) or getattr(job, "next_fire_time", None)
        if next_time is None:
            return None
        return next_time.astimezone(_safe_zone(timezone)).replace(tzinfo=None)

    async def trigger_now(self) -> None:
        await self._job()

    async def _job(self) -> None:
        logger.info("开始执行定时签到")
        try:
            logs = await run_all_tasks(trigger="scheduled")
            logger.info("定时签到完成，共 %s 条记录", len(logs))
        except Exception:  # noqa: BLE001 - never let the scheduler die
            logger.exception("定时签到执行异常")


checkin_scheduler = CheckinScheduler()
