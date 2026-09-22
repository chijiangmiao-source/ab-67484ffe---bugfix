"""基本语义：发号、幂等重放、内容冲突、查询接口、参数校验。"""
import httpx

from server_util import allocate


def test_first_allocation_starts_at_one(server):
    resp = allocate(server.base_url, "S1", "op-1", notes="开场")
    assert resp.status_code == 201
    body = resp.json()
    assert body["shot_number"] == 1
    assert body["replayed"] is False
    assert body["scene_id"] == "S1"
    assert body["client_op_id"] == "op-1"


def test_identical_retry_replays_original_number(server):
    first = allocate(server.base_url, "S1", "op-1", notes="全景")
    again = allocate(server.base_url, "S1", "op-1", notes="全景")
    assert again.status_code == 200
    assert again.json()["shot_number"] == first.json()["shot_number"]
    assert again.json()["replayed"] is True
    # 重放不占新号：下一个新操作仍拿到 2
    nxt = allocate(server.base_url, "S1", "op-2", notes="特写")
    assert nxt.json()["shot_number"] == 2


def test_same_op_id_with_different_content_conflicts(server):
    assert allocate(server.base_url, "S1", "op-1", notes="版本A").status_code == 201
    conflict = allocate(server.base_url, "S1", "op-1", notes="版本B")
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert detail["error"] == "payload_conflict"
    assert detail["existing"]["notes"] == "版本A"
    # 冲突不影响后续发号
    assert allocate(server.base_url, "S1", "op-2", notes="版本B").json()["shot_number"] == 2


def test_numbers_are_consecutive_per_scene_and_independent(server):
    for i in range(1, 4):
        assert allocate(server.base_url, "SA", f"a-{i}").json()["shot_number"] == i
    # 另一个场次独立从 1 开始
    assert allocate(server.base_url, "SB", "b-1").json()["shot_number"] == 1


def test_list_and_get_endpoints(server):
    allocate(server.base_url, "S1", "op-1", notes="甲")
    allocate(server.base_url, "S1", "op-2", notes="乙")
    listing = httpx.get(f"{server.base_url}/api/scenes/S1/shot-numbers")
    assert listing.status_code == 200
    items = listing.json()
    assert [it["shot_number"] for it in items] == [1, 2]
    assert [it["notes"] for it in items] == ["甲", "乙"]

    got = httpx.get(f"{server.base_url}/api/operations/op-2")
    assert got.status_code == 200
    assert got.json()["shot_number"] == 2
    assert httpx.get(f"{server.base_url}/api/operations/nope").status_code == 404


def test_validation_rejects_bad_payloads(server):
    assert allocate(server.base_url, "", "op-1").status_code == 422
    assert allocate(server.base_url, "S1", "").status_code == 422
    assert httpx.post(
        f"{server.base_url}/api/shot-numbers", json={"scene_id": "S1"}, timeout=10
    ).status_code == 422
