"""RECOVERY-GAP 场景的自动化验收。

覆盖：
- 空库首次提交即注入提交后故障：503 后号码与操作映射已共同持久化；
- 按操作标识查询立即可见，场次列表从 1 开始连续；
- 进程重启后，携带原注入标志重试仍只取回原号码（200 + replayed），不再触发故障；
- 并发不同操作中混入一次提交后中断，全部成功操作的号码无重复、无缺口。
"""
from __future__ import annotations

import concurrent.futures as futures

import httpx

from server_util import RunningServer, allocate

SCENE = "RECOVERY-GAP"
OP = "op-recovery-gap-1"
NOTES = "雨夜跟拍"
INJECTED_PAYLOAD = {
    "scene_id": SCENE,
    "client_op_id": OP,
    "notes": NOTES,
    "inject_failure_after_commit": True,
}


def _numbers(items: list[dict]) -> list[int]:
    return [item["shot_number"] for item in items]


def test_injected_first_request_is_durable_across_lookup_restart_and_flagged_retry(db_path):
    # 空数据库启动（fixture 每次使用独立的临时文件）
    srv = RunningServer(db_path).start()
    try:
        # 1. 首次请求按设计返回 503
        first = httpx.post(f"{srv.base_url}/api/shot-numbers", json=INJECTED_PAYLOAD, timeout=10)
        assert first.status_code == 503
        assert first.json()["detail"]["error"] == "injected_failure_after_commit"

        # 2. 503 之时映射已经落库：按操作标识查询可取回 1 号，而非 404
        stored = httpx.get(f"{srv.base_url}/api/operations/{OP}", timeout=10)
        assert stored.status_code == 200
        stored_body = stored.json()
        assert stored_body["shot_number"] == 1
        assert stored_body["scene_id"] == SCENE
        assert stored_body["notes"] == NOTES

        # 3. 场次列表中 1 号已存在，从 1 开始严格连续
        listing = httpx.get(f"{srv.base_url}/api/scenes/{SCENE}/shot-numbers", timeout=10)
        assert listing.status_code == 200
        assert _numbers(listing.json()) == [1]
    finally:
        srv.stop()

    # 4. 重启 API 进程
    srv2 = RunningServer(db_path).start()
    try:
        # 5. 保持故障注入标志再次重试：取回首次结果，不允许再次 503
        retry = httpx.post(f"{srv2.base_url}/api/shot-numbers", json=INJECTED_PAYLOAD, timeout=10)
        assert retry.status_code == 200
        retry_body = retry.json()
        assert retry_body["shot_number"] == 1
        assert retry_body["replayed"] is True

        # 6. 随后另一条不同操作取得 2 号
        nxt = allocate(srv2.base_url, SCENE, "op-recovery-gap-2", notes="雨停补拍")
        assert nxt.status_code == 201
        assert nxt.json()["shot_number"] == 2
        assert nxt.json()["replayed"] is False

        # 7. 列表最终为从 1 开始的严格连续序列，不缺 1 号
        final = httpx.get(f"{srv2.base_url}/api/scenes/{SCENE}/shot-numbers", timeout=10)
        assert _numbers(final.json()) == [1, 2]
    finally:
        srv2.stop()


def test_concurrent_different_ops_with_one_post_commit_interruption_are_gapless(server):
    scene = "S-concurrent-interrupt"
    interrupted_op = "op-interrupted"

    # 19 条普通操作 + 1 条注入提交后故障的操作，共 20 个不同操作并发提交
    payloads = [
        {
            "scene_id": scene,
            "client_op_id": interrupted_op,
            "notes": "跟拍中断",
            "inject_failure_after_commit": True,
        }
    ]
    payloads += [
        {"scene_id": scene, "client_op_id": f"op-{i}", "notes": f"镜头{i}"}
        for i in range(1, 20)
    ]

    with futures.ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(
            pool.map(
                lambda p: httpx.post(f"{server.base_url}/api/shot-numbers", json=p, timeout=30),
                payloads,
            )
        )

    statuses = sorted(r.status_code for r in responses)
    # 恰好一次 503（数值上排在 201 之后），其余 19 条全部首次创建成功
    assert statuses == [201] * 19 + [503]

    created_numbers = [r.json()["shot_number"] for r in responses if r.status_code == 201]

    # 中断的操作重试取回原号码（不带标志亦可，此处显式不带）
    retry = allocate(server.base_url, scene, interrupted_op, notes="跟拍中断")
    assert retry.status_code == 200
    assert retry.json()["replayed"] is True
    recovered_number = retry.json()["shot_number"]

    # 所有成功操作（含中断后恢复的那条）的号码集合：无重复、无缺口
    all_numbers = sorted(created_numbers + [recovered_number])
    assert all_numbers == list(range(1, 21))
    # 恢复的是 503 当次已提交、却未在 201 响应中返回的那个号码，重试并未新占号
    assert recovered_number not in created_numbers
    assert len(set(created_numbers)) == 19

    listing = httpx.get(f"{server.base_url}/api/scenes/{scene}/shot-numbers", timeout=10)
    assert _numbers(listing.json()) == list(range(1, 21))
