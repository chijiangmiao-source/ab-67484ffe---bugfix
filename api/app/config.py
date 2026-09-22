"""运行时配置：数据库路径与开发模式开关。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str
    dev_mode: bool

    @classmethod
    def from_env(cls, db_path: str | None = None, dev_mode: bool | None = None) -> "Settings":
        path = db_path or os.environ.get("DB_PATH", "./data/shotnumbers.db")
        if dev_mode is None:
            dev_mode = os.environ.get("DEV_MODE", "").strip().lower() in ("1", "true", "yes", "on")
        return cls(db_path=path, dev_mode=dev_mode)
