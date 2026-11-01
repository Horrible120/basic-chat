# 基础聊天室

Vue 3 + Vite 前端，FastAPI + WebSocket 后端。消息只保存在进程内，服务重启或页面刷新后不会恢复历史记录。

## 环境

- Python 3.11+
- Node.js 18+
- npm（或 pnpm）
- `cloudflared`（仅公网临时访问需要）

如果 Windows 没有 `npm`，请重新安装 Node.js 并勾选加入 PATH；也可以使用项目环境中的 `pnpm`。

## 快速开始

首次安装依赖：

```powershell
.\scripts\setup.ps1
```

开发模式（两个服务，打开 `http://localhost:5173`）：

```powershell
.\scripts\dev.ps1
```

构建并以 FastAPI 提供网页（打开 `http://127.0.0.1:8000`）：

```powershell
.\scripts\start.ps1
```

另开终端启动 Cloudflare Quick Tunnel：

```powershell
.\scripts\tunnel.ps1
```

脚本会打印临时的 `trycloudflare.com` 地址。Quick Tunnel 适合开发和演示，停止 `cloudflared` 后地址失效。

## 手动命令

```powershell
python -m pip install -r backend/requirements.txt
pnpm --dir frontend install
pnpm --dir frontend build
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cloudflared tunnel --url http://127.0.0.1:8000
```

测试：

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -q
```

## 智能体入口

应用内置一个常驻智能体（默认名「小深」），采用 Router + Worker 双层结构：

- 在房间消息里发送 `@小深 帮我看下 backend/main.py`，或点击输入框左侧的 `@` 按钮；
- 右侧 Agent 面板可以直接私聊、查看任务状态与执行步骤、停止任务；
- Router 负责对话与分派，Worker 在独立上下文中并发执行，互不阻塞；
- 同一会话线程的后续消息会直通已订阅的 Worker，不再重复经过 Router。

首次使用需要配置模型密钥：

```powershell
Copy-Item .env.example .env
# 编辑 .env，填写 LLM_API_KEY=sk-...
```

未配置密钥时进入演示模式：前后端链路仍可跑通，但只会返回配置提示。`.env` 已被 `.gitignore` 忽略。

### 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_API_KEY` | 空 | DeepSeek 或任意 OpenAI 兼容服务的密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com` | 兼容接口地址（含 `/v1` 亦可） |
| `AGENT_NAME` | `小深` | 智能体昵称，同时作为 @ 触发词 |
| `ROUTER_MODEL` | `deepseek-flash` | Router 层模型 |
| `WORKER_MODEL` | `deepseek-flash` | Worker 默认模型 |
| `WORKER_MODEL_HEAVY` | `deepseek-v4-pro` | Router 判定为 heavy 的任务使用的模型 |
| `ROUTER_THINKING` | `disabled` | Router 是否开启 DeepSeek 思考模式 |
| `WORKER_THINKING` | `enabled` | Worker 是否开启思考模式 |
| `REASONING_EFFORT` | `high` | 思考强度：`low` / `high` / `max` |
| `MAX_WORKERS` | `3` | 并行 Worker 上限 |
| `MAX_STEPS` | `8` | 单个 Worker 的最大工具调用轮数 |
| `AGENT_ALLOW_WRITE` | `true` | 是否允许内置 Worker 写工作区文件 |
| `DSH_ENABLED` | `false` | 是否用 DeepSeek Harness 执行任务 |
| `DSH_COMMAND` | `dsh` | Harness CLI 路径或命令名 |
| `DSH_PROFILE` | `headless` | Harness profile |
| `DSH_PROVIDER` | `deepseek-official` | Harness 模型提供方 |
| `DSH_EXTRA_ARGS` | 空 | 追加给 headless 的参数 |
| `DSH_TIMEOUT` | `1800` | 单次 Harness 执行超时（秒） |

Router 默认关闭思考以保证分派速度；Worker 默认开启。DeepSeek 在思考模式下带 `tools` 请求时要求回传 `reasoning_content`，代码已按此处理。

Worker 可用工具：读取会话/消息/任务、列出目录、读取文件、写入文件。写入范围限制在项目目录内，`.git`、`.env`、`.venv`、`node_modules`、`tools` 等路径被拒绝。

### 使用 DeepSeek Harness 执行任务（可选）

安装 Node.js 22.19+ 和 DeepSeek Harness：

```powershell
npm install -g @deepseek-ai/dsh
dsh --version
```

然后在 `.env` 中设置：

```ini
DSH_ENABLED=true
DSH_COMMAND=dsh
DSH_PROFILE=headless
```

满足条件时，Worker 会调用 `dsh --profile headless --json` 执行任务，获得 Harness 的编码工具、沙箱和会话恢复能力；找不到 `dsh` 时自动回退到内置 Worker。

- 每个任务一个 Harness Session，任务 ID 作为 `--session-id`，同一任务的补充消息继续原会话；
- 单次 headless 调用只执行一个任务，结束后进程退出，结果通过 NDJSON 事件流回传；
- 当前 0.2.1-rc.5 的 headless 只支持 `--json` 和 `--session-id`；如果版本支持权限参数，可通过 `DSH_EXTRA_ARGS` 追加。

### 当前限制

- 会话与任务保存在进程内，服务重启后丢失（P2 计划迁移到 SQLite）；
- 尚无 Watchdog 与投机执行（P3）；
- 无用户鉴权，私聊线程按连接标识隔离，重连后历史不可恢复；
- Harness 后端的 Session 由 `dsh` 自己持久化，但任务卡片状态仍保存在本进程内。

## WebSocket 协议

连接 `/ws?nickname=昵称`。客户端发送 `{ "type": "chat", "content": "消息" }`；服务端发送 `ready`、`chat`、`presence`、`error` 事件。昵称长度为 1–20，消息长度为 1–2000，均按纯文本处理。

智能体相关扩展：

```jsonc
// 客户端
{ "type": "agent.dm", "content": "帮我写个脚本" }
{ "type": "agent.stop", "taskId": "task_xxx" }

// 服务端
{ "type": "agent.message", ... }   // 私聊消息回显
{ "type": "agent.delta", ... }     // 流式增量
{ "type": "agent.state", ... }     // 任务状态
{ "type": "agent.trace", ... }     // Worker 工具调用记录
{ "type": "agent.done", ... }      // 最终回复
{ "type": "agent.error", ... }     // 智能体错误
```

