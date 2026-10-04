"""Check-in task CRUD and manual execution."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_current_user, get_db
from ..models import Account, Task, User
from ..runner import run_all_tasks, run_task_by_id
from ..schemas import MessageResponse, RunOut, TaskCreate, TaskOut, TaskUpdate

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class ReorderRequest(BaseModel):
    ids: list[int]


async def _validate_account(session: AsyncSession, payload: TaskCreate | TaskUpdate) -> None:
    """An explicit account must exist; omitting it means "use the default one"."""
    if payload.account_id is None:
        return
    if await session.get(Account, payload.account_id) is None:
        raise HTTPException(400, "所选 Telegram 账号不存在")


def _validate_task(payload: TaskCreate | TaskUpdate) -> None:
    """Cross-field validation that pydantic alone cannot express."""
    if payload.target_type == "bot":
        if not payload.bot_username:
            raise HTTPException(400, "机器人任务必须填写机器人用户名")
    elif payload.target_type == "group":
        if not payload.group_id:
            raise HTTPException(400, "群组任务必须填写群组 ID")
        if payload.action_type != "message":
            raise HTTPException(400, "群组任务只支持「发送消息」类型")
    else:
        raise HTTPException(400, "未知的目标类型")

    if payload.action_type == "message" and not (payload.message or "").strip():
        raise HTTPException(400, "消息内容不能为空")

    if payload.action_type == "button":
        if payload.button_type == "text" and not (payload.button_text or "").strip():
            raise HTTPException(400, "文本按钮必须填写按钮文本")
        if payload.button_type == "callback" and not (payload.callback_data or "").strip():
            raise HTTPException(400, "回调按钮必须填写回调数据")


def _apply_payload(task: Task, payload: TaskCreate | TaskUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    for field in (
        "name",
        "enabled",
        "account_id",
        "target_type",
        "bot_username",
        "group_id",
        "action_type",
        "message",
        "button_type",
        "button_text",
        "callback_data",
        "start_command",
        "auto_captcha",
    ):
        if field in data:
            setattr(task, field, data[field])

    # keep the record consistent with the selected target / action
    if task.target_type == "bot":
        task.group_id = None
    else:
        task.bot_username = None
        task.start_command = None
        task.action_type = "message"
        task.button_type = None
        task.button_text = None
        task.callback_data = None

    if task.action_type == "message":
        task.button_type = None
        task.button_text = None
        task.callback_data = None
    else:
        task.message = None

    task.name = (task.name or "").strip() or (task.bot_username or task.group_id or "未命名任务")
    task.updated_at = datetime.utcnow()


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    account_id: int | None = Query(default=None, description="按账号过滤"),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Task).order_by(Task.sort_order, Task.id)
    if account_id is not None:
        stmt = stmt.where(Task.account_id == account_id)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _validate_task(payload)
    await _validate_account(session, payload)
    task = Task()
    _apply_payload(task, payload)

    max_order = await session.scalar(select(func.coalesce(func.max(Task.sort_order), 0)))
    task.sort_order = int(max_order or 0) + 1

    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    return task


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    _validate_task(payload)
    await _validate_account(session, payload)
    _apply_payload(task, payload)
    await session.commit()
    await session.refresh(task)
    return task


@router.delete("/{task_id}", response_model=MessageResponse)
async def delete_task(
    task_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    await session.delete(task)
    await session.commit()
    return MessageResponse(ok=True, message="任务已删除")


@router.post("/{task_id}/toggle", response_model=TaskOut)
async def toggle_task(
    task_id: int,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    task.enabled = not task.enabled
    task.updated_at = datetime.utcnow()
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/{task_id}/run", response_model=RunOut)
async def run_task(
    task_id: int,
    _: User = Depends(get_current_user),
):
    try:
        log = await run_task_by_id(task_id, trigger="manual")
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return log


@router.post("/run-all", response_model=list[RunOut])
async def run_all(
    account_id: int | None = Query(default=None, description="只运行该账号下的任务"),
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    logs = await run_all_tasks(trigger="manual", account_id=account_id)
    return logs


@router.post("/reorder", response_model=MessageResponse)
async def reorder_tasks(
    payload: ReorderRequest,
    session: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Persist the drag-and-drop order."""
    for index, task_id in enumerate(payload.ids):
        task = await session.get(Task, int(task_id))
        if task is not None:
            task.sort_order = index
    await session.commit()
    return MessageResponse(ok=True, message="顺序已保存")
