"""开发模式故障注入：首次持久提交后返回 503，重试只取回原号码且不再触发。"""
import httpx

from server_util import RunningServer, allocate


def test_injected_failure_commits_once_and_replays_without_refailing(server):
    payload = dict(scene_id="S-inj", client_op_id="op-inj-1", notes="雨夜",
                   inject_failure_after_commit=True)

    first = httpx.post(f"{server.base_url}/api/shot-numbers", json=payload, timeout=10)
    assert first.status_code == 503
    assert first.json()["detail"]["error"] == "injected_failure_after_commit"

    # 503 不代表未生效：号码已持久化
    stored = httpx.get(f"{server.base_url}/api/operations/op-inj-1")
    assert stored.status_code == 200
    assert stored.json()["shot_number"] == 1

    # 带着注入标志重试同内容：只取回原号码，不再触发故障
    retry = httpx.post(f"{server.base_url}/api/shot-numbers", json=payload, timeout=10)
    assert retry.status_code == 200
    assert retry.json()["shot_number"] == 1
    assert retry.json()["replayed"] is True

    # 不带标志重试亦如此
    retry2 = allocate(server.base_url, "S-inj", "op-inj-1", notes="雨夜")
    assert retry2.status_code == 200
    assert retry2.json()["shot_number"] == 1

    # 无缺口：下一个新操作拿到 2
    nxt = allocate(server.base_url, "S-inj", "op-inj-2", notes="续拍")
    assert nxt.status_code == 201
    assert nxt.json()["shot_number"] == 2


def test_inject_flag_ignored_outside_dev_mode(db_path):
    srv = RunningServer(db_path, dev_mode=False).start()
    try:
        resp = httpx.post(
            f"{srv.base_url}/api/shot-numbers",
            json={"scene_id": "S1", "client_op_id": "op-1",
                  "inject_failure_after_commit": True},
            timeout=10,
        )
        assert resp.status_code == 201
        assert resp.json()["shot_number"] == 1
    finally:
        srv.stop()


def test_recovery_gap_scenario_across_restart_with_flagged_retry(db_path):
    """从空库走完整 RECOVERY-GAP 场景：首次注入 503 时 1 号与操作映射已共同持久化；
    重启后携带原故障标志重试仍取回 1 号（重放、不再触发故障），后续发号严格连续。"""
    payload = dict(scene_id="RECOVERY-GAP", client_op_id="op-rain-night",
                   notes="雨夜跟拍", inject_failure_after_commit=True)

    srv = RunningServer(db_path).start()
    first = httpx.post(f"{srv.base_url}/api/shot-numbers", json=payload, timeout=10)
    assert first.status_code == 503
    assert first.json()["detail"]["error"] == "injected_failure_after_commit"

    # 503 不代表未生效：按操作标识查询应返回已持久化的 1 号，而非 404
    stored = httpx.get(f"{srv.base_url}/api/operations/op-rain-night", timeout=10)
    assert stored.status_code == 200
    assert stored.json()["shot_number"] == 1
    srv.stop()  # 进程重启，仅凭数据库恢复

    srv2 = RunningServer(db_path).start()
    try:
        # 携带原故障注入标志重试同一操作：200 + 镜号 1 + 重放标记，不再触发故障
        retry = httpx.post(f"{srv2.base_url}/api/shot-numbers", json=payload, timeout=10)
        assert retry.status_code == 200
        assert retry.json()["shot_number"] == 1
        assert retry.json()["replayed"] is True

        # 下一条不同操作取得 2 号
        nxt = allocate(srv2.base_url, "RECOVERY-GAP", "op-daylight", notes="清晨补拍")
        assert nxt.status_code == 201
        assert nxt.json()["shot_number"] == 2

        # 场次列表从 1 开始严格连续，不缺 1 号
        listing = httpx.get(f"{srv2.base_url}/api/scenes/RECOVERY-GAP/shot-numbers", timeout=10)
        assert listing.status_code == 200
        assert [item["shot_number"] for item in listing.json()] == [1, 2]
    finally:
        srv2.stop()
