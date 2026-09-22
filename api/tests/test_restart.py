"""进程重启：操作映射与场次计数完全由数据库恢复。"""
from server_util import RunningServer, allocate


def test_restart_preserves_mappings_and_counter(db_path):
    srv = RunningServer(db_path).start()
    assert allocate(srv.base_url, "S1", "op-a", notes="开场").json()["shot_number"] == 1
    assert allocate(srv.base_url, "S1", "op-b", notes="追车").json()["shot_number"] == 2
    srv.stop()

    # 同一数据库文件上重新启动进程
    srv2 = RunningServer(db_path).start()
    try:
        replay = allocate(srv2.base_url, "S1", "op-a", notes="开场")
        assert replay.status_code == 200
        assert replay.json()["shot_number"] == 1
        assert replay.json()["replayed"] is True

        # 冲突检测同样跨重启有效
        assert allocate(srv2.base_url, "S1", "op-a", notes="改过的内容").status_code == 409

        # 计数器不回退：新操作继续从 3 开始
        nxt = allocate(srv2.base_url, "S1", "op-c", notes="收尾")
        assert nxt.status_code == 201
        assert nxt.json()["shot_number"] == 3
    finally:
        srv2.stop()


def test_restart_after_injected_crash_recovers_original_number(db_path):
    srv = RunningServer(db_path).start()
    payload = dict(scene_id="S9", client_op_id="op-crash", notes="爆破",
                   inject_failure_after_commit=True)
    import httpx

    resp = httpx.post(f"{srv.base_url}/api/shot-numbers", json=payload, timeout=10)
    assert resp.status_code == 503  # 提交后、回包前“崩溃”
    srv.stop()  # 模拟进程退出

    srv2 = RunningServer(db_path).start()
    try:
        # 现场以为号码未生效而重试 —— 取回的仍是最初的号码
        retry = allocate(srv2.base_url, "S9", "op-crash", notes="爆破")
        assert retry.status_code == 200
        assert retry.json()["shot_number"] == 1
        # 且该号码不会被重复发放
        assert allocate(srv2.base_url, "S9", "op-next").json()["shot_number"] == 2
    finally:
        srv2.stop()
