import type { AllocateRequest, Allocation, ShotNumberItem } from "./types";

/** 网络层失败（请求根本没得到响应） */
export class NetworkError extends Error {}

/** 服务端返回的错误，status 为 HTTP 状态码 */
export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

/** 409：同一 client_op_id 携带了不同内容 */
export class ConflictError extends ApiError {}

/** 503：服务暂时不可用（含注入的“提交后崩溃”故障），可安全重试 */
export class ServiceUnavailableError extends ApiError {}

declare global {
  // 测试环境（Vitest）通过该全局变量注入真实 API 地址
  // eslint-disable-next-line no-var
  var __API_ORIGIN__: string | undefined;
}

function apiBase(): string {
  const injected = globalThis.__API_ORIGIN__;
  if (injected) return `${injected}/api`;
  const fromEnv = (import.meta.env?.VITE_API_ORIGIN as string | undefined) ?? "";
  if (fromEnv) return `${fromEnv.replace(/\/$/, "")}/api`;
  return "/api";
}

async function parseError(res: Response): Promise<never> {
  let code = "unknown";
  let message = `请求失败（HTTP ${res.status}）`;
  try {
    const body = await res.json();
    if (body?.detail?.code || body?.detail?.error) {
      code = body.detail.code ?? body.detail.error;
    }
    if (body?.detail?.message) message = body.detail.message;
  } catch {
    /* 保留默认信息 */
  }
  if (res.status === 409) throw new ConflictError(409, code, message);
  if (res.status === 503) throw new ServiceUnavailableError(503, code, message);
  throw new ApiError(res.status, code, message);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${apiBase()}${path}`, init);
  } catch (err) {
    throw new NetworkError(
      `无法连接服务：${err instanceof Error ? err.message : String(err)}`,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as T;
}

export function allocateShotNumber(req: AllocateRequest): Promise<Allocation> {
  return request<Allocation>("/shot-numbers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
}

export function listShotNumbers(sceneId: string): Promise<ShotNumberItem[]> {
  return request<ShotNumberItem[]>(
    `/scenes/${encodeURIComponent(sceneId)}/shot-numbers`,
  );
}
