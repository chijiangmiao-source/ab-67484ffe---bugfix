import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  allocateShotNumber,
  ConflictError,
  listShotNumbers,
  NetworkError,
  ServiceUnavailableError,
} from "./api";
import type { Allocation, ShotNumberItem } from "./types";

interface PendingOp {
  client_op_id: string;
  scene_id: string;
  notes: string;
  inject: boolean;
}

type ErrorKind = "conflict" | "unavailable" | "network" | "unknown";
interface ErrorState {
  kind: ErrorKind;
  message: string;
}

const PENDING_KEY = "shotnumbers.pendingOp.v1";

function newOpId(): string {
  // crypto.randomUUID 仅在安全上下文可用（compose 内 http://web 并非安全上下文），需兜底
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
}

function loadPending(): PendingOp | null {
  try {
    const raw = localStorage.getItem(PENDING_KEY);
    return raw ? (JSON.parse(raw) as PendingOp) : null;
  } catch {
    return null;
  }
}

function savePending(op: PendingOp | null) {
  try {
    if (op) localStorage.setItem(PENDING_KEY, JSON.stringify(op));
    else localStorage.removeItem(PENDING_KEY);
  } catch {
    /* 存储不可用时仅保留内存态 */
  }
}

export default function App() {
  const restored = useRef<PendingOp | null>(loadPending());
  const [sceneId, setSceneId] = useState(restored.current?.scene_id ?? "");
  const [notes, setNotes] = useState(restored.current?.notes ?? "");
  const [inject, setInject] = useState(restored.current?.inject ?? false);
  const [pending, setPending] = useState<PendingOp | null>(restored.current);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ErrorState | null>(null);
  const [result, setResult] = useState<Allocation | null>(null);
  const [issued, setIssued] = useState<ShotNumberItem[]>([]);

  const refreshIssued = useCallback(async (scene: string) => {
    if (!scene) {
      setIssued([]);
      return;
    }
    try {
      setIssued(await listShotNumbers(scene));
    } catch {
      /* 列表刷新失败不影响主流程 */
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void refreshIssued(sceneId.trim()), 250);
    return () => clearTimeout(timer);
  }, [sceneId, refreshIssued]);

  async function attempt(op: PendingOp) {
    setSubmitting(true);
    setError(null);
    try {
      const alloc = await allocateShotNumber({
        scene_id: op.scene_id,
        client_op_id: op.client_op_id,
        notes: op.notes,
        inject_failure_after_commit: op.inject,
      });
      setResult(alloc);
      setPending(null);
      savePending(null);
      void refreshIssued(op.scene_id);
    } catch (err) {
      // 失败一律保留待重试操作，由用户决定何时重试
      if (err instanceof ConflictError) {
        setError({ kind: "conflict", message: err.message });
      } else if (err instanceof ServiceUnavailableError) {
        setError({
          kind: "unavailable",
          message: `${err.message}。操作已保留，可安全重试：同一操作标识不会重复占号。`,
        });
      } else if (err instanceof NetworkError) {
        setError({
          kind: "network",
          message: `${err.message}。操作已保留，恢复网络后可安全重试。`,
        });
      } else {
        setError({
          kind: "unknown",
          message: err instanceof Error ? err.message : String(err),
        });
      }
    } finally {
      setSubmitting(false);
    }
  }

  function buildOp(opId: string): PendingOp {
    return {
      client_op_id: opId,
      scene_id: sceneId.trim(),
      notes,
      inject,
    };
  }

  function handleSubmit(ev: FormEvent) {
    ev.preventDefault();
    if (submitting) return;
    // 有待重试操作时复用其 client_op_id —— 重试同一逻辑操作而非新建操作
    const op = buildOp(pending?.client_op_id ?? newOpId());
    setPending(op);
    savePending(op);
    void attempt(op);
  }

  function handleResubmitAsNew() {
    if (submitting) return;
    const op = buildOp(newOpId());
    setPending(op);
    savePending(op);
    void attempt(op);
  }

  function handleDiscardPending() {
    setPending(null);
    savePending(null);
    setError(null);
  }

  const canSubmit = !submitting && sceneId.trim().length > 0;

  return (
    <main className="page">
      <h1>场记镜号发放</h1>
      <p className="hint">
        同一操作标识（client_op_id）无论重试多少次，只会领取到一个镜号。
      </p>

      <form onSubmit={handleSubmit} className="card">
        <label htmlFor="scene">场次</label>
        <input
          id="scene"
          value={sceneId}
          onChange={(e) => setSceneId(e.target.value)}
          placeholder="例如 S12-夜-仓库"
          required
        />

        <label htmlFor="notes">备注</label>
        <textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="镜头内容备注（可空）"
          rows={2}
        />

        <label className="inline" htmlFor="inject">
          <input
            id="inject"
            type="checkbox"
            checked={inject}
            onChange={(e) => setInject(e.target.checked)}
          />
          注入提交后故障（开发模式）
        </label>

        {pending && (
          <div className="banner pending" data-testid="pending-banner">
            <span>
              有待重试的操作 <code>{pending.client_op_id.slice(0, 8)}…</code>
              ，重试将沿用原操作标识，不会重复占号。
            </span>
            <button type="button" className="link" onClick={handleDiscardPending}>
              放弃该操作
            </button>
          </div>
        )}

        {error && (
          <div className={`banner error`} data-testid={`error-${error.kind}`} role="alert">
            {error.kind === "conflict" ? (
              <>
                <strong>内容冲突：</strong>
                {error.message}
                <button
                  type="button"
                  className="link"
                  onClick={handleResubmitAsNew}
                  disabled={submitting}
                >
                  以新操作重新提交
                </button>
              </>
            ) : (
              <>
                <strong>提交失败：</strong>
                {error.message}
              </>
            )}
          </div>
        )}

        <button type="submit" disabled={!canSubmit}>
          {submitting ? "提交中…" : pending ? "重试领取镜号" : "领取镜号"}
        </button>
      </form>

      {result && (
        <section className="card result" data-testid="result-card">
          <div className="shot">镜号 #{result.shot_number}</div>
          <div className="meta">
            场次 {result.scene_id} ・ 操作 {result.client_op_id.slice(0, 8)}…
            {result.replayed && <span className="tag">重放结果，未重复占号</span>}
          </div>
        </section>
      )}

      <section className="card">
        <h2>本场次已发放{sceneId.trim() ? `（${sceneId.trim()}）` : ""}</h2>
        {issued.length === 0 ? (
          <p className="hint">暂无已发放镜号</p>
        ) : (
          <table data-testid="issued-table">
            <thead>
              <tr>
                <th>镜号</th>
                <th>备注</th>
                <th>操作标识</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              {issued.map((item) => (
                <tr key={item.client_op_id} data-testid="issued-row">
                  <td>#{item.shot_number}</td>
                  <td>{item.notes || "—"}</td>
                  <td>
                    <code>{item.client_op_id.slice(0, 8)}…</code>
                  </td>
                  <td>{item.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
