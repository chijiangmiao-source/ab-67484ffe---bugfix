"""对 docker compose 拉起的真实服务做冒烟验收（设置 API_ORIGIN 时启用）。"""
import os
import uuid

import httpx
import pytest

API_ORIGIN = os.environ.get("API_ORIGIN")

pytestmark = pytest.mark.skipif(not API_ORIGIN, reason="API_ORIGIN 未设置，跳过组合服务冒烟")


def test_composed_service_end_to_end():
    scene = f"smoke-{uuid.uuid4()}"
    op = f"op-{uuid.uuid4()}"
    resp = httpx.post(
        f"{API_ORIGIN}/api/shot-numbers",
        json={"scene_id": scene, "client_op_id": op, "notes": "冒烟"},
        timeout=10,
    )
    assert resp.status_code == 201
    assert resp.json()["shot_number"] == 1
    replay = httpx.post(
        f"{API_ORIGIN}/api/shot-numbers",
        json={"scene_id": scene, "client_op_id": op, "notes": "冒烟"},
        timeout=10,
    )
    assert replay.status_code == 200
    assert replay.json()["shot_number"] == 1
