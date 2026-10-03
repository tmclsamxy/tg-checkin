"""Application settings.

All values can be overridden through environment variables or a `.env` file
placed next to the backend package (see `.env.example`).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- app ----
    app_name: str = "TG Checkin"
    app_version: str = "2.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # ---- storage ----
    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("DATA_DIR", "./data")))
    database_url: str = ""

    # ---- security ----
    secret_key: str = ""
    admin_username: str = "admin"
    admin_password: str = ""
    access_token_expire_minutes: int = 720

    # ---- defaults ----
    default_timezone: str = "Asia/Shanghai"
    default_schedule_time: str = "08:00"

    @model_validator(mode="after")
    def _prepare(self) -> "Settings":
        self.data_dir = Path(self.data_dir).expanduser().resolve()
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeError(_data_dir_help(self.data_dir, exc)) from exc

        # 容器以非 root 用户运行，挂载的宿主目录常常是其写不进去的，
        # 否则后面只会抛出一个看不懂的 PermissionError。
        if not os.access(self.data_dir, os.W_OK | os.X_OK):
            raise RuntimeError(_data_dir_help(self.data_dir, None))

        if not self.database_url:
            self.database_url = f"sqlite+aiosqlite:///{self.data_dir / 'tgcheckin.db'}"

        if not self.secret_key:
            key_file = self.data_dir / ".secret_key"
            if key_file.exists():
                self.secret_key = key_file.read_text(encoding="utf-8").strip()
            if not self.secret_key:
                self.secret_key = secrets.token_urlsafe(48)
                key_file.write_text(self.secret_key, encoding="utf-8")
                try:
                    os.chmod(key_file, 0o600)
                except OSError:  # pragma: no cover - Windows
                    pass
        return self


def _data_dir_help(path: Path, error: Exception | None) -> str:
    detail = f"（{error}）" if error else ""
    return (
        f"数据目录不可写：{path} {detail}\n"
        "容器以 uid 10001 运行，而 bind mount 的宿主目录通常是 Docker 以 root 创建的。\n"
        "解决办法二选一：\n"
        f"  1. 在宿主机执行：chown -R 10001:10001 <你挂载的目录>\n"
        "  2. 改用 Docker 具名卷（Docker 会自动继承镜像内的属主）：\n"
        "       volumes:\n"
        "         - tg-checkin-data:/app/data\n"
        "       volumes:\n"
        "         tg-checkin-data:"
    )


settings = Settings()
