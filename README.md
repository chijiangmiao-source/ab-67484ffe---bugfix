# 场记镜号发放（Shot Number Issuance）

片场多台场记终端为同一场次领取镜号的全栈小系统：React/TypeScript 页面 + FastAPI +
SQLite（WAL，持久化卷）。核心保证：

- 每个场次的镜号从 **1** 开始**严格连续**发放；
- 同一 `client_op_id` + 相同内容，无论并发、重试还是进程重启，都返回**最初分配的号码**（幂等重放）；
- 同一 `client_op_id` 携带**不同内容** → **409**；
- 不同操作并发成功后所得号码集合**无重复、无缺口**，号码顺序即数据库事务提交顺序；
- 操作映射与场次计数**只存于数据库**，不增加任何 worker，进程重启后据此恢复。

## 快速开始（Docker Compose）

```bash
docker compose up --build api web   # 页面 http://localhost:8080 ，API http://localhost:8000
```

宿主端口可用环境变量覆盖：

```bash
WEB_PORT=9000 API_PORT=9001 docker compose up --build api web
```

数据保存在命名卷 `api-data`（容器内 `/data/app.db`），`docker compose down` 后仍在；
`docker compose down -v` 才会清空。

## 一次性验收

`verify` 服务依赖 `api` 与 `web`，启动时会自动拉起整套环境，跑完所有检查即退出：

```bash
docker compose up --build --abort-on-container-exit --exit-code-from verify verify
```

`verify` 服务在 compose 网络内依次执行（任一失败即非零退出）：

1. 冒烟检查 `api` / `web` 可达；
2. **pytest**：20 并发无重复无缺口、并发重复重试共享号码、进程重启后映射与计数恢复、
   注入故障只触发一次、409 冲突、参数校验（另含对 compose 服务的端到端冒烟）；
3. **Vitest**：前端 API 客户端与页面组件对**真实运行的 API** 联调（重试、冲突、并发）；
4. **Playwright**：真实浏览器验证“失败后保留待重试操作 → 恢复后取回唯一镜号”、
   冲突错误反馈与“以新操作重新提交”。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/shot-numbers` | 领取镜号。新操作 → `201`；同标识同内容重放 → `200`；同标识不同内容 → `409`；注入故障 → `503` |
| GET | `/api/scenes/{scene_id}/shot-numbers` | 某场次已发放镜号列表（按号码升序） |
| GET | `/api/operations/{client_op_id}` | 查询单个操作映射（不存在 → `404`） |
| GET | `/api/health` | 健康检查 |

```bash
curl -X POST http://localhost:8000/api/shot-numbers \
  -H 'Content-Type: application/json' \
  -d '{"scene_id":"S12-夜-仓库","client_op_id":"'"$(uuidgen)"'","notes":"开场航拍"}'
# {"scene_id":"S12-夜-仓库","client_op_id":"…","notes":"开场航拍","shot_number":1,"replayed":false}
```

## 事务边界

发号接口的全部副作用都在**同一个 SQLite 事务**内完成（`api/app/service.py`）：

```
BEGIN IMMEDIATE                       -- 事务开始即取得写锁，发放事务彼此严格串行
  1. SELECT operations WHERE client_op_id = ?
       命中且内容哈希一致 → COMMIT，重放原号码（200）
       命中但内容哈希不同 → ROLLBACK，409
  2. INSERT OR IGNORE scene_counters (scene_id, next_number = 1)
  3. SELECT next_number → 本次镜号 N
  4. UPDATE scene_counters SET next_number = N + 1
  5. INSERT operations (client_op_id, scene_id, notes, payload_hash, shot_number = N)
COMMIT                                -- 提交点即号码生效点
```

- **为什么 `BEGIN IMMEDIATE`**：事务一开始就取得数据库级写锁，所有发号事务按到达
  顺序串行执行，因此“号码分配顺序 == 事务提交顺序”，并发下既不重复也不跳号；
  同时避免了“先读后写”事务在升级写锁时的快照冲突。
- **为什么无缺口**：计数器递增（第 4 步）与操作映射写入（第 5 步）在同一事务中，
  要么一起提交、要么一起回滚，不存在“占了号却没落库”的中间态。
- **持久性**：连接统一设置 `journal_mode=WAL`、`synchronous=FULL`，`COMMIT` 返回时
  数据已落盘；此后即使进程崩溃（回包前崩溃也一样），重启后仍能从数据库取回原号码。
- **兜底约束**：`operations.client_op_id` 主键、`(scene_id, shot_number)` 唯一约束，
  由数据库最终保证不重号。
- 读接口（列表/单查/健康检查）在事务外自动提交模式下执行，不参与发号串行化。

## 开发模式故障注入

为可重复验收“落库后、回包前崩溃”的场景，开发模式（`DEV_MODE=1`，compose 默认开启）
下请求可携带：

```json
{"scene_id":"S1","client_op_id":"op-1","notes":"爆破","inject_failure_after_commit":true}
```

该操作**首次完成持久提交后**返回 `503`（号码已生效，但客户端无法得知）；此后用同一
`client_op_id` 重试（无论是否再带该标志）只会取回原号码，且**不会再次触发故障**。
非开发模式下该标志被忽略。页面上的“注入提交后故障”勾选项即此开关。

## 本地开发

```bash
# API（Python 3.11+）
cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements-test.txt
DB_PATH=./data/dev.db DEV_MODE=1 .venv/bin/uvicorn app.main:app --port 8000
.venv/bin/python -m pytest -v            # 并发 / 重启 / 故障注入测试

# Web（Node 20+）
cd web && npm install
API_PORT=8000 npm run dev                # http://localhost:5173 ，/api 代理到 API
npm test                                 # Vitest：自动拉起真实 API（或 API_ORIGIN=http://localhost:8000 复用现有服务）
npx playwright install chromium && npm run e2e   # Playwright：自动拉起 API 与 vite
```

## 目录结构

```
api/            FastAPI 应用（app/）与 pytest 测试（tests/）
  app/service.py    发号事务（幂等检查 + 计数器 + 映射写入）
web/            React/TypeScript 页面、Vitest 用例（src/__tests__/）、Playwright 用例（e2e/）
verify/         一次性验收服务（Dockerfile + 执行脚本）
docker-compose.yml
```

## 环境变量

| 变量 | 作用域 | 默认 | 说明 |
| --- | --- | --- | --- |
| `WEB_PORT` | compose | `8080` | 页面宿主端口 |
| `API_PORT` | compose / vite | `8000` | API 宿主端口（本地开发时也是 vite 代理目标） |
| `DB_PATH` | api | `/data/app.db`（容器） | SQLite 数据库文件路径 |
| `DEV_MODE` | api | 关（compose 中开） | 开启后接受 `inject_failure_after_commit` |
| `API_ORIGIN` | verify / vitest | — | 指向已运行的 API（如 `http://api:8000`） |
| `E2E_BASE_URL` | verify / playwright | — | 指向已运行的页面（如 `http://web`） |
