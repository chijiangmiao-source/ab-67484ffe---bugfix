import { describe, expect, it } from "vitest";
import {
  allocateShotNumber,
  ConflictError,
  listShotNumbers,
  ServiceUnavailableError,
} from "../api";

const scene = () => `vitest-${crypto.randomUUID()}`;
const opId = () => crypto.randomUUID();

describe("allocateShotNumber（真实 API 联调）", () => {
  it("从 1 开始发号，相同重试取回原号码", async () => {
    const s = scene();
    const req = { scene_id: s, client_op_id: opId(), notes: "全景" };
    const first = await allocateShotNumber(req);
    expect(first.shot_number).toBe(1);
    expect(first.replayed).toBe(false);

    const retry = await allocateShotNumber(req);
    expect(retry.shot_number).toBe(1);
    expect(retry.replayed).toBe(true);

    const second = await allocateShotNumber({
      scene_id: s,
      client_op_id: opId(),
      notes: "特写",
    });
    expect(second.shot_number).toBe(2);
  });

  it("同一标识换内容抛 409 冲突", async () => {
    const s = scene();
    const id = opId();
    await allocateShotNumber({ scene_id: s, client_op_id: id, notes: "版本A" });
    await expect(
      allocateShotNumber({ scene_id: s, client_op_id: id, notes: "版本B" }),
    ).rejects.toBeInstanceOf(ConflictError);
  });

  it("注入故障只生效一次，重试取回原号码且不再触发", async () => {
    const s = scene();
    const req = {
      scene_id: s,
      client_op_id: opId(),
      notes: "航拍",
      inject_failure_after_commit: true,
    };
    await expect(allocateShotNumber(req)).rejects.toBeInstanceOf(
      ServiceUnavailableError,
    );
    // 重试仍带注入标志：只能取回原号码，不再 503
    const recovered = await allocateShotNumber(req);
    expect(recovered.shot_number).toBe(1);
    expect(recovered.replayed).toBe(true);
    // 无缺口
    const next = await allocateShotNumber({
      scene_id: s,
      client_op_id: opId(),
      notes: "跟进",
    });
    expect(next.shot_number).toBe(2);
  });

  it("20 个并发不同操作所得集合无重复、无缺口", async () => {
    const s = scene();
    const results = await Promise.all(
      Array.from({ length: 20 }, (_, i) =>
        allocateShotNumber({
          scene_id: s,
          client_op_id: opId(),
          notes: `op-${i}`,
        }),
      ),
    );
    const numbers = results.map((r) => r.shot_number).sort((a, b) => a - b);
    expect(numbers).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));

    const listed = await listShotNumbers(s);
    expect(listed.map((it) => it.shot_number)).toEqual(numbers);
  });
});
