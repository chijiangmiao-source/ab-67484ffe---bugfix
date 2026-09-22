import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach } from "vitest";

// 把 globalSetup 选定的真实 API 地址注入浏览器侧代码可见的全局变量
const origin =
  process.env.API_ORIGIN ??
  readFileSync(path.resolve(process.cwd(), ".vitest-api-origin"), "utf8").trim();
(globalThis as Record<string, unknown>).__API_ORIGIN__ = origin;

afterEach(() => cleanup());
