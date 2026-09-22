"""FastAPI 应用工厂与路由。"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from . import service
from .config import Settings
from .db import make_engine
from .schemas import AllocateRequest, AllocationResponse, ShotNumberItem


def _to_item(op: dict) -> ShotNumberItem:
    return ShotNumberItem(**op)


def create_app(db_path: str | None = None, dev_mode: bool | None = None) -> FastAPI:
    settings = Settings.from_env(db_path, dev_mode)
    engine = make_engine(settings.db_path)

    app = FastAPI(title="Shot Number Issuance", version="1.0.0")
    app.state.engine = engine
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/api/shot-numbers", response_model=AllocationResponse, status_code=201)
    def allocate(req: AllocateRequest, response: Response) -> AllocationResponse:
        try:
            result = service.allocate_shot_number(
                engine,
                scene_id=req.scene_id,
                client_op_id=req.client_op_id,
                notes=req.notes,
                interrupt_after_commit=req.inject_failure_after_commit and settings.dev_mode,
            )
        except service.PayloadConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "payload_conflict",
                    "message": "client_op_id 已被不同内容占用，请更换操作标识",
                    "client_op_id": exc.client_op_id,
                    "existing": {"scene_id": exc.existing_scene_id, "notes": exc.existing_notes},
                },
            ) from exc
        except service.PostCommitUnavailableError as exc:
            # 事务已持久提交（号码已生效），此处模拟进程在回包前崩溃：
            # 客户端无法得知结果，只能凭 client_op_id 重试取回原号码。
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "injected_failure_after_commit",
                    "message": "注入故障：提交已持久化，响应返回前服务不可用",
                },
            ) from exc

        response.status_code = 200 if not result.created else 201
        return AllocationResponse(
            scene_id=result.scene_id,
            client_op_id=result.client_op_id,
            notes=result.notes,
            shot_number=result.shot_number,
            replayed=not result.created,
        )

    @app.get("/api/scenes/{scene_id}/shot-numbers", response_model=list[ShotNumberItem])
    def list_scene_shot_numbers(scene_id: str) -> list[ShotNumberItem]:
        return [_to_item(op) for op in service.list_shot_numbers(engine, scene_id)]

    @app.get("/api/operations/{client_op_id}", response_model=ShotNumberItem)
    def get_operation(client_op_id: str) -> ShotNumberItem:
        op = service.get_operation(engine, client_op_id)
        if op is None:
            raise HTTPException(status_code=404, detail={"error": "not_found"})
        return _to_item(op)

    return app


app = create_app()
