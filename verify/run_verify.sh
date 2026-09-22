#!/usr/bin/env bash
# 一次性验收：任一阶段失败即非零退出。
set -euo pipefail

echo "=== [1/4] 冒烟检查：api / web 可达 ==="
curl -fsS --retry 20 --retry-delay 1 --retry-all-errors "${API_ORIGIN}/api/health"
echo
curl -fsS --retry 20 --retry-delay 1 --retry-all-errors -o /dev/null "${E2E_BASE_URL}/"

echo "=== [2/4] pytest：API 并发 / 幂等 / 重启 / 故障注入 ==="
cd /verify/api && python3 -m pytest -v

echo "=== [3/4] Vitest：前端与真实 API 联调 ==="
cd /verify/web && npx vitest run

echo "=== [4/4] Playwright：浏览器端重试与错误反馈 ==="
cd /verify/web && npx playwright test

echo "=============================================="
echo "  ALL CHECKS PASSED"
echo "=============================================="
