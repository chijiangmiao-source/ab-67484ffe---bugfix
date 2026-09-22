import { defineConfig, devices } from "@playwright/test";

// verify 服务中通过 E2E_BASE_URL 指向 compose 内的 web 服务；
// 本地默认自动拉起 vite 开发服务器与一个临时数据库的 API 进程。
const externalBase = process.env.E2E_BASE_URL;
const python = process.env.PYTHON ?? "python3";

export default defineConfig({
  testDir: "./e2e",
  timeout: 30000,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? "line" : "list",
  use: {
    baseURL: externalBase ?? "http://127.0.0.1:5173",
    trace: "retain-on-failure",
  },
  webServer: externalBase
    ? undefined
    : [
        {
          command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 18010`,
          cwd: "../api",
          env: {
            DB_PATH: `/tmp/shotnumbers-e2e-${process.pid}.db`,
            DEV_MODE: "1",
          },
          port: 18010,
          reuseExistingServer: false,
        },
        {
          command: "npm run dev -- --port 5173 --strictPort",
          env: { API_PORT: "18010" },
          port: 5173,
          reuseExistingServer: !process.env.CI,
        },
      ],
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
