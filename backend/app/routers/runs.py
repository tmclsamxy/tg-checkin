"""Run history endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import RunLog, User
from ..schemas import MessageResponse, RunOut, RunStats

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
async def list_runs(
    task_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    limit = max(1, min(limit, 500))
    stmt = select(RunLog).order_by(RunLog.created_at.desc(), RunLog.id.desc())
    if task_id is not None:
        stmt = stmt.where(RunLog.task_id == task_id)
    if status:
        stmt = stmt.where(RunLog.status == status)
    result = await session.execute(stmt.limit(limit).offset(offset))
    return result.scalars().all()


@router.get("/stats", response_model=RunStats)
async def stats(
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    total_rows = await session.execute(
        select(RunLog.status, func.count(RunLog.id)).group_by(RunLog.status)
    )
    counts = {row[0]: row[1] for row in total_rows.fetchall()}

    since = datetime.utcnow() - timedelta(hours=24)
    today_rows = await session.execute(
        select(RunLog.status, func.count(RunLog.id))
        .where(RunLog.created_at >= since)
        .group_by(RunLog.status)
    )
    today = {row[0]: row[1] for row in today_rows.fetchall()}

    return RunStats(
        total=sum(counts.values()),
        success=counts.get("success", 0),
        failed=counts.get("failed", 0),
        skipped=counts.get("skipped", 0),
        today_total=sum(today.values()),
        today_success=today.get("success", 0),
        today_failed=today.get("failed", 0),
    )


@router.delete("", response_model=MessageResponse)
async def clear_runs(
    days: int | None = None,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from sqlalchemy import delete

    stmt = delete(RunLog)
    if days and days > 0:
        stmt = stmt.where(RunLog.created_at < datetime.utcnow() - timedelta(days=days))
    await session.execute(stmt)
    await session.commit()
    return MessageResponse(ok=True, message="日志已清理")
