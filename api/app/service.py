"""镜号发放的核心事务逻辑。

事务边界（见 README）：
    BEGIN IMMEDIATE
        1. 按 client_op_id 查操作映射 —— 命中则校验内容哈希并直接重放原号码；
        2. 否则在同一事务内读取并递增场次计数器、写入操作映射；
    COMMIT  —— 提交点即号码生效点，之后即使进程崩溃结果也已持久化。

BEGIN IMMEDIATE 在事务开始时即取得数据库写锁，使所有发放事务严格串行：
号码分配顺序 == 事务提交顺序，且并发下不会重复、不会跳号。
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from .models import Operation, SceneCounter


class PayloadConflictError(Exception):
    """同一 client_op_id 携带了与首次提交不同的内容。"""

    def __init__(self, client_op_id: str, existing_scene_id: str, existing_notes: str):
        self.client_op_id = client_op_id
        self.existing_scene_id = existing_scene_id
        self.existing_notes = existing_notes
        super().__init__(f"client_op_id {client_op_id!r} already used with different payload")


class PostCommitUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class Allocation:
    scene_id: str
    client_op_id: str
    notes: str
    shot_number: int
    created: bool  # True=本次新发放；False=重放既有映射


_allocation_gate = threading.Lock()


def content_hash(scene_id: str, notes: str) -> str:
    canonical = json.dumps(
        {"scene_id": scene_id, "notes": notes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def allocate_shot_number(
    engine: Engine,
    *,
    scene_id: str,
    client_op_id: str,
    notes: str,
    interrupt_after_commit: bool = False,
) -> Allocation:
    """在单个 IMMEDIATE 事务内完成幂等检查与发号，提交后返回。"""
    digest = content_hash(scene_id, notes)
    with _allocation_gate:
        with engine.connect() as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                existing = conn.execute(
                    select(
                        Operation.shot_number,
                        Operation.payload_hash,
                        Operation.scene_id,
                        Operation.notes,
                    ).where(Operation.client_op_id == client_op_id)
                ).mappings().first()
                if existing is not None:
                    if existing["payload_hash"] != digest:
                        raise PayloadConflictError(
                            client_op_id, existing["scene_id"], existing["notes"]
                        )
                    conn.exec_driver_sql("COMMIT")
                    return Allocation(
                        scene_id, client_op_id, notes, existing["shot_number"], created=False
                    )

                conn.execute(
                    sqlite_insert(SceneCounter)
                    .values(scene_id=scene_id, next_number=1)
                    .on_conflict_do_nothing()
                )
                number = conn.execute(
                    select(SceneCounter.next_number).where(SceneCounter.scene_id == scene_id)
                ).scalar_one()
                conn.execute(
                    update(SceneCounter)
                    .where(SceneCounter.scene_id == scene_id)
                    .values(next_number=number + 1)
                )
                conn.execute(
                    insert(Operation).values(
                        client_op_id=client_op_id,
                        scene_id=scene_id,
                        notes=notes,
                        payload_hash=digest,
                        shot_number=number,
                    )
                )
                conn.exec_driver_sql("COMMIT")
            except Exception:
                conn.exec_driver_sql("ROLLBACK")
                raise

    # 提交点即号码生效点：计数器与操作映射已在同一事务中共同持久化，
    # 注入故障只模拟“落库后、回包前崩溃”，此后重试凭 client_op_id 取回原号码。
    if interrupt_after_commit:
        raise PostCommitUnavailableError()

    return Allocation(scene_id, client_op_id, notes, number, created=True)


_OPERATION_COLUMNS = (
    Operation.scene_id,
    Operation.client_op_id,
    Operation.notes,
    Operation.shot_number,
    Operation.created_at,
)


def list_shot_numbers(engine: Engine, scene_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(*_OPERATION_COLUMNS)
            .where(Operation.scene_id == scene_id)
            .order_by(Operation.shot_number)
        ).mappings().all()
        return [dict(row) for row in rows]


def get_operation(engine: Engine, client_op_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(*_OPERATION_COLUMNS).where(Operation.client_op_id == client_op_id)
        ).mappings().first()
        return dict(row) if row is not None else None
