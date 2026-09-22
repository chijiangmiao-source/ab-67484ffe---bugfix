"""并发语义：不同操作无重复无缺口；相同操作的并发重试共享同一号码。"""
import concurrent.futures as futures

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
