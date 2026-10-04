"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from .config import settings
from .database import SessionLocal, dispose_db, init_db
from .models import User
from .routers import accounts, auth, runs, settings as settings_router, system, tasks
from .scheduler import checkin_scheduler
from .security import hash_password
from .settings_store import get_app_settings
from .telegram.manager import telegram_manager

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("tgcheckin")

# Built frontend assets (see frontend/vite.config.js -> outDir)
FRONTEND_DIST = Path(__file__).resolve().parent / "static"


async def _seed_admin() -> None:
    async with SessionLocal() as session:
        existing = (await session.execute(select(User))).scalars().first()
        if existing is not None:
            return
        password = settings.admin_password or "admin123"
        user = User(
            username=settings.admin_username,
            password_hash=hash_password(password),
            must_change_password=not bool(settings.admin_password),
        )
        session.add(user)
        await session.commit()
        if not settings.admin_password:
            logger.warning("已创建默认管理员 %s / admin123 —— 请登录后立即修改密码", user.username)
        else:
            logger.info("已创建管理员账号 %s", user.username)


async def _restore_telegram() -> None:
    """Best-effort: reconnect every saved session so the panel is ready immediately."""
    try:
        await telegram_manager.restore_all()
    except Exception as exc:  # noqa: BLE001
        logger.info("Telegram 账号未自动连接（%s），请在面板中完成登录", exc)


async def _bootstrap_scheduler() -> None:
    async with SessionLocal() as session:
        cfg = await get_app_settings(session)
    checkin_scheduler.apply(
        enabled=cfg.schedule_enabled, schedule_time=cfg.schedule_time, timezone=cfg.timezone
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await _seed_admin()
    await _bootstrap_scheduler()
    await _restore_telegram()
    yield
    await telegram_manager.disconnect()
    checkin_scheduler.shutdown()
    await dispose_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": settings.app_version}

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):  # pragma: no cover - safety net
        logger.exception("未处理异常: %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "服务器内部错误"}, status_code=500)

    app.include_router(auth.router)
    app.include_router(accounts.router)
    app.include_router(settings_router.router)
    app.include_router(tasks.router)
    app.include_router(runs.router)
    app.include_router(system.router)

    if FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/favicon.svg")
        async def favicon():
            return FileResponse(FRONTEND_DIST / "favicon.svg")

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            index = FRONTEND_DIST / "index.html"
            target = FRONTEND_DIST / full_path
            if full_path and target.is_file() and target.suffix:
                return FileResponse(target)
            return FileResponse(index)
    else:

        @app.get("/")
        async def root():
            return {
                "name": settings.app_name,
                "version": settings.app_version,
                "hint": "前端静态文件未构建，请执行 frontend 目录中的构建步骤，或访问 /api/docs",
            }

    return app


app = create_app()
