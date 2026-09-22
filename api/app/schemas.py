"""请求/响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AllocateRequest(BaseModel):
    scene_id: str = Field(min_length=1, max_length=128)
    client_op_id: str = Field(min_length=1, max_length=64)
    notes: str = Field(default="", max_length=2000)
    # 仅开发模式生效：首次持久提交后、回包前注入 503，模拟进程崩溃
    inject_failure_after_commit: bool = False


class AllocationResponse(BaseModel):
    scene_id: str
    client_op_id: str
    notes: str
    shot_number: int
    replayed: bool  # True 表示该 client_op_id 的重放，未重复占号


class ShotNumberItem(BaseModel):
    scene_id: str
    client_op_id: str
    notes: str
    shot_number: int
    created_at: datetime
