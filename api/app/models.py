"""持久化模型：操作映射（幂等键 -> 镜号）与场次计数器。

数据库是这两份数据的唯一权威存储，进程重启后据此恢复。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SceneCounter(Base):
    """每个场次一行，next_number 为下一个待发放的镜号（从 1 开始）。"""

    __tablename__ = "scene_counters"

    scene_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)


class Operation(Base):
    """client_op_id -> 已发放镜号的不可变映射，同时记录内容哈希用于冲突检测。"""

    __tablename__ = "operations"

    client_op_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("scene_id", "shot_number", name="uq_operations_scene_shot"),
    )
