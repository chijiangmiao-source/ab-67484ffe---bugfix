"""并发语义：不同操作无重复无缺口；相同操作的并发重试共享同一号码。"""
import concurrent.futures as futures

import httpx

from server_util import allocate


def test_twenty_concurrent_operations_get_gapless_unique_numbers(server):
    scene = "S-concurrent"
    with futures.ThreadPoolExecutor(max_workers=20) as pool:
        calls = [
            pool.submit(allocate, server.base_url, scene, f"op-{i}", f"镜头{i}")
            for i in range(20)
        ]
        responses = [c.result() for c in calls]
    assert all(r.status_code in (200, 201) for r in responses)
    numbers = sorted(r.json()["shot_number"] for r in responses)
    assert numbers == list(range(1, 21))
    assert sum(1 for r in responses if r.status_code == 201) == 20


def test_concurrent_duplicate_retries_share_one_number(server):
    scene = "S-duplicates"
    # 5 个不同操作，每个并发重复提交 4 次（模拟超时重试风暴）
    tasks = [(f"dup-op-{i}", f"备注{i}") for i in range(5) for _ in range(4)]
    with futures.ThreadPoolExecutor(max_workers=20) as pool:
        calls = [pool.submit(allocate, server.base_url, scene, op, notes) for op, notes in tasks]
        responses = [c.result() for c in calls]

    by_op: dict[str, set[int]] = {}
    for (op, _), resp in zip(tasks, responses):
        assert resp.status_code in (200, 201)
        by_op.setdefault(op, set()).add(resp.json()["shot_number"])

    # 每个操作无论重试多少次都只拿到一个号码
    assert all(len(numbers) == 1 for numbers in by_op.values())
    # 5 个操作占满 1..5，无重复无缺口
    assert sorted(next(iter(n)) for n in by_op.values()) == [1, 2, 3, 4, 5]
    # 恰好 5 次为首次创建，其余均为重放
    assert sum(1 for r in responses if r.status_code == 201) == 5
    assert sum(1 for r in responses if r.status_code == 200) == 15


def test_concurrent_load_across_multiple_scenes(server):
    scenes = ["S-x", "S-y"]
    tasks = [(scene, f"{scene}-op-{i}") for scene in scenes for i in range(10)]
    with futures.ThreadPoolExecutor(max_workers=20) as pool:
        calls = [pool.submit(allocate, server.base_url, scene, op) for scene, op in tasks]
        responses = [c.result() for c in calls]
    for scene in scenes:
        numbers = sorted(
            r.json()["shot_number"]
            for (s, _), r in zip(tasks, responses)
            if s == scene
        )
        assert numbers == list(range(1, 11))


def test_concurrent_operations_with_one_post_commit_interruption(server):
    """并发不同操作中混入一次提交后中断：中断操作的号码已随事务持久化，
    重试（仍携带故障标志）取回原号码后，全部成功操作的号码集合无重复、无缺口。"""
    scene = "S-concurrent-inj"
    total = 12
    payload = dict(scene_id=scene, client_op_id="op-inj-mid", notes="雨夜跟拍",
                   inject_failure_after_commit=True)

    def submit(i: int):
        if i == 0:
            return i, httpx.post(
                f"{server.base_url}/api/shot-numbers", json=payload, timeout=30
            )
        return i, allocate(server.base_url, scene, f"op-{i}", f"镜头{i}")

    with futures.ThreadPoolExecutor(max_workers=total) as pool:
        responses = dict(pool.map(submit, range(total)))

    # 恰好注入一次故障：该操作首次返回 503，其余并发操作全部成功
    interrupted = responses.pop(0)
    assert interrupted.status_code == 503
    assert all(r.status_code == 201 for r in responses.values())

    # 503 不代表未生效：按操作标识可查到已持久化的号码
    stored = httpx.get(f"{server.base_url}/api/operations/op-inj-mid", timeout=10)
    assert stored.status_code == 200
    persisted = stored.json()["shot_number"]

    # 携带原故障标志重试：取回同一号码、标记重放、不再触发故障
    retry = httpx.post(f"{server.base_url}/api/shot-numbers", json=payload, timeout=10)
    assert retry.status_code == 200
    assert retry.json()["shot_number"] == persisted
    assert retry.json()["replayed"] is True

    # 全部成功操作的号码集合无重复、无缺口
    numbers = {r.json()["shot_number"] for r in responses.values()}
    numbers.add(persisted)
    assert sorted(numbers) == list(range(1, total + 1))

    # 场次列表从 1 开始严格连续
    listing = httpx.get(f"{server.base_url}/api/scenes/{scene}/shot-numbers", timeout=10)
    assert [item["shot_number"] for item in listing.json()] == list(range(1, total + 1))
