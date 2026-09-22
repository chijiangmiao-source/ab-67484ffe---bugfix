/**
 * Vitest 全局装配：为测试准备一个真实运行的 FastAPI 服务。
 * - 若设置了 API_ORIGIN（如 docker compose 的 verify 服务），直接使用该服务；
 * - 否则在本地临时数据库文件上启动一个 uvicorn 进程。
 * 选定的地址写入 .vitest-api-origin，由 vitest.setup.ts 读入测试进程。
 */
import { spawn } from "node:child_process";
import { writeFileSync, rmSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";

const MARKER = path.resolve(process.cwd(), ".vitest-api-origin");

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(port));
    });
  });
}

async function waitHealthy(origin: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${origin}/api/health`);
      if (res.ok) return;
    } catch {
      /* 尚未就绪 */
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`API at ${origin} did not become healthy`);
}

export default async function setup(): Promise<() => Promise<void>> {
  const external = process.env.API_ORIGIN;
  if (external) {
    await waitHealthy(external, 30000);
    writeFileSync(MARKER, external);
    return async () => rmSync(MARKER, { force: true });
  }

  const port = await freePort();
  const dbPath = path.join(
    os.tmpdir(),
    `shotnumbers-vitest-${process.pid}-${Date.now()}.db`,
  );
  const apiDir = path.resolve(process.cwd(), "..", "api");
  const python = process.env.PYTHON ?? "python3";
  const proc = spawn(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)],
    {
      cwd: apiDir,
      env: { ...process.env, DB_PATH: dbPath, DEV_MODE: "1" },
      stdio: "ignore",
    },
  );
  const origin = `http://127.0.0.1:${port}`;
  await waitHealthy(origin, 30000);
  writeFileSync(MARKER, origin);

  return async () => {
    proc.kill("SIGTERM");
    rmSync(MARKER, { force: true });
    for (const suffix of ["", "-wal", "-shm"]) {
      rmSync(`${dbPath}${suffix}`, { force: true });
    }
  };
}
