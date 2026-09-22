import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发服务器把 /api 代理到本地 API（端口可用 API_PORT 覆盖）
const apiPort = process.env.API_PORT ?? "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
});
