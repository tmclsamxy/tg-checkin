"""Import tasks from the legacy ``checkin_tasks.json`` file.

Usage:
    # from the repository root, against the running instance's database
    python tools/import_legacy.py ../telegram/checkin_tasks.json

    # or point at another data directory
    DATA_DIR=/var/lib/tgcheckin python tools/import_legacy.py tasks.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal, dispose_db, init_db  # noqa: E402
from app.models import Task  # noqa: E402


def convert(raw: dict) -> Task:
    target_type = raw.get("target_type", "bot")
    action_type = raw.get("type", "message")

    task = Task(
        name=raw.get("remark") or "",
        enabled=True,
        target_type=target_type if target_type in ("bot", "group") else "bot",
        bot_username=raw.get("bot_username"),
        group_id=str(raw["group_id"]) if raw.get("group_id") is not None else None,
        action_type=action_type if action_type in ("message", "button") else "message",
        message=raw.get("message"),
        button_type=raw.get("button_type"),
        button_text=raw.get("button_text"),
        callback_data=raw.get("callback_data"),
        start_command=raw.get("start_command"),
    )

    # normalise the bot username the same way the API does
    if task.bot_username and not task.bot_username.startswith("@"):
        task.bot_username = f"@{task.bot_username}"

    if task.target_type == "group":
        task.bot_username = None
        task.action_type = "message"
        task.button_type = None
        task.button_text = None
        task.callback_data = None

    if task.action_type == "message":
        task.button_type = None
        task.button_text = None
        task.callback_data = None

    task.name = (task.name or "").strip() or (task.bot_username or task.group_id or "未命名任务")
    return task


async def run(path: Path, *, dry_run: bool) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("tasks", [])
    if not isinstance(payload, list):
        raise SystemExit("无法识别的文件格式，期望一个任务数组")

    def signature(t: Task) -> tuple:
        """Identity of a task — the same bot may legitimately have several actions."""
        return (
            t.target_type,
            t.bot_username,
            t.group_id,
            t.action_type,
            t.message,
            t.button_type,
            t.button_text,
            t.callback_data,
            t.start_command,
        )

    await init_db()
    imported = 0
    async with SessionLocal() as session:
        max_order = await session.scalar(select(Task.sort_order).order_by(Task.sort_order.desc()).limit(1)) or 0
        existing = {
            signature(t) for t in (await session.execute(select(Task))).scalars().all()
        }

        for index, raw in enumerate(payload, start=1):
            task = convert(raw)
            target = task.bot_username or task.group_id
            if signature(task) in existing:
                print(f"  跳过（已存在）: {task.name} -> {target}")
                continue

            task.sort_order = max_order + index
            existing.add(signature(task))
            imported += 1
            print(f"  + {task.name} -> {target}")
            if not dry_run:
                session.add(task)

        if not dry_run:
            await session.commit()

    await dispose_db()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="导入旧版 checkin_tasks.json")
    parser.add_argument("file", type=Path, help="旧版 checkin_tasks.json 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要导入的任务，不写入数据库")
    args = parser.parse_args()

    if not args.file.exists():
        raise SystemExit(f"文件不存在: {args.file}")

    print(f"数据库目录: {os.getenv('DATA_DIR', './data')}")
    count = asyncio.run(run(args.file, dry_run=args.dry_run))
    suffix = "（dry-run，未写入）" if args.dry_run else ""
    print(f"完成：导入 {count} 个任务{suffix}")


if __name__ == "__main__":
    main()
