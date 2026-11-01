# 在「基础聊天室」中接入 Super-agent：设计与实施计划

> 目标：在现有 Vue 3 + FastAPI 聊天室中，加入一个常驻的「超级智能体」聊天入口，并按 Super-agent 的五个基础模块（双层架构、事件驱动、面向人的交互、存算分离、Watchdog）逐步落地。

---

## 实现状态

- ✅ **P0 骨架与最小闭环**：DeepSeek 兼容流式客户端、@ 触发过滤、Router 对话、流式回复
- ✅ **P1 Worker 与任务面板**：并发 Worker、Thread 订阅直通、任务状态/执行记录、停止任务
- ✅ **P1.5 Harness Worker**：DeepSeek Harness `headless --json` 执行后端、按任务切换 Flash/Pro、思考模式与 `reasoning_content` 兼容
- ⏳ P2 持久化与链式召回
- ⏳ P3 主动性与 Watchdog
- ⏳ P4 外部信道与安全加固

默认已开启工作区文件读写（`AGENT_ALLOW_WRITE=true`），可用环境变量关闭。当前批次处理为顺序执行，尚未合并进单次 Router 调用。

---

## 1. 现状盘点

| 层 | 现状 | 对 Agent 的影响 |
| --- | --- | --- |
| 后端 | `backend/main.py`，单个 `/ws` 房间，`ConnectionManager` 广播 | 已有统一出口，可直接复用为 Agent 的「信道」 |
| 消息 | 仅进程内列表语义，无持久化 | 重启即丢失，无法做连续上下文，需要补存储 |
| 协议 | `{type, content}`，服务端下发 `ready/presence/chat/error` | `type` 可扩展，前端按类型分发已具备 |
| 前端 | Vue 3 单页 + `useChat.js` composable | 加 Agent 面板成本低，无需引入路由/状态库 |
| 认证 | 无，凭昵称加入 | Agent 入口需要至少「谁在和它说话」的标识 |
| 依赖 | `fastapi` + `uvicorn`，前端仅 `vue` | 需新增 LLM 客户端与 SQLite 驱动 |

**结论**：现有代码是一个干净的最小内核，适合作为 Super-agent 的「信道层」，但缺少三样东西：**持久化状态**、**Agent 运行时**、**任务/会话的可视化**。

---

## 2. 目标形态

同一个智能体，两个入口，共享同一份全局上下文：

1. **房间内 @ 触发**（公开信道）
   `@小深 帮我把这段话翻译成英文`
   → 生成 Trigger，Router 判断后分派 Worker，结果回到房间。

2. **Agent 面板私聊**（私密信道）
   右侧抽屉，可直接对话、查看任务列表与执行状态、停止任务。
   → 同一条 Thread 内的后续消息**直通**已订阅的 Worker，不再经过 Router。

```
┌──────────────────────── 浏览器 ────────────────────────┐
│  聊天室（公开）              │  Agent 面板（私密）        │
│  @小深 ...                   │  对话 / 任务 / 停止        │
└──────────────┬───────────────┴────────────┬─────────────┘
               │        WebSocket /ws        │
┌──────────────▼─────────────────────────────▼─────────────┐
│ FastAPI 进程                                             │
│  ┌──────────────┐   Trigger   ┌───────────────────────┐  │
│  │ 过滤 FastPath│────────────▶│ Router Session (常驻) │  │
│  │ + SlowPath   │             │ 分派 / 汇总 / 对外回复 │  │
│  └──────────────┘             └───────┬───────────────┘  │
│                             订阅直通   │ 新建任务          │
│                        ┌──────────────▼───────────────┐  │
│                        │ Worker A / B / C（上下文隔离）│  │
│                        │ 工具：start/stop/read_*      │  │
│                        └──────────────┬───────────────┘  │
│  ┌──────────────┐   ┌─────────────────▼───────────────┐  │
│  │ Watchdog     │   │ Store（SQLite：thread/task/msg）│  │
│  └──────────────┘   └─────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**关键边界**：Worker 不直接写 WebSocket，只向 Router 汇报；Router 统一对外输出。这样多个 Worker 并发时不会出现「多个声音同时说话」。

---

## 3. 模块映射

| 文章中的模块 | 本项目落地 | 文件 |
| --- | --- | --- |
| 双层架构 · Router | 单常驻 asyncio 会话 + 有界队列，积压自动合并 | `backend/agent/router.py` |
| 双层架构 · Worker | 每任务一个隔离会话，`asyncio.Semaphore` 限并发 | `backend/agent/worker.py` |
| Harness Worker | `dsh --profile headless --json`，按任务写 `--patch` 选择模型 | `backend/agent/dsh.py` |
| 事件过滤 | 程序规则（@、私聊、白名单）+ LLM 语义判定 | `backend/agent/filters.py` |
| 订阅与直通 | `Thread → Worker` 映射，命中则绕过 Router | `backend/agent/registry.py` |
| Inline & Spill / 链式召回 | 注入最近 N 条 + 关联 ID，提供 `read_thread/read_message/read_task` | `backend/agent/context.py` |
| 异步 ReAct | `start_task()` 立即返回 Started，结果作为新事件回灌 | `backend/agent/loop.py` |
| 多信道输出 | 按来源渲染：房间简短、面板结构化 | `backend/agent/context.py` 提示词 |
| 存算分离 | 会话/任务落 SQLite，进程可重启恢复 | `backend/store.py` |
| Watchdog | 心跳 + 超时 + 无进展检测，可自动取消/重启 Worker | `backend/agent/watchdog.py` |
| 外部信道（GitHub/IM） | 适配器接口，后续接入 | `backend/channels/` |

---

## 4. 协议扩展（向后兼容）

### 客户端 → 服务端

```jsonc
{ "type": "chat", "content": "@小深 你好" }          // 现有，房间广播
{ "type": "agent.dm", "threadId": "dm:u123", "content": "帮我写个脚本" }
{ "type": "agent.stop", "taskId": "task_abc" }
{ "type": "agent.ack", "taskId": "task_abc" }        // 确认/验收
```

### 服务端 → 客户端

```jsonc
{ "type": "agent.reply",  "threadId": "...", "channel": "room|dm", "messageId": "...", "content": "..." }
{ "type": "agent.delta",  "taskId": "...", "messageId": "...", "content": "增量 token" }
{ "type": "agent.state",  "taskId": "...", "status": "queued|running|done|failed|stopped", "title": "..." }
{ "type": "agent.trace",  "taskId": "...", "step": "tool:read_thread", "detail": "..." }
{ "type": "agent.done",   "taskId": "...", "messageId": "...", "content": "最终结果" }
```

前端 `useChat.js` 增加一个 `agents` 响应式对象：
`replies / tasks / deltas / traces`，与现有 `messages` 并列。

**Thread 的划分**：
- 房间公开消息 → `threadId = room:main`
- Agent 面板 → `threadId = dm:<userId>`
- 未来 GitHub → `threadId = gh:pr:<repo>#<num>`

同一 Thread 的后续 Trigger 若已有订阅 Worker，则直通（Fast Path）；否则交 Router（Slow Path）。

---

## 5. 数据模型（SQLite / aiosqlite）

```sql
threads(id TEXT PK, kind TEXT, title TEXT, created_at TEXT, updated_at TEXT)
messages(id TEXT PK, thread_id TEXT, role TEXT, author TEXT, content TEXT, created_at TEXT)
tasks(id TEXT PK, thread_id TEXT, title TEXT, status TEXT,
      worker_id TEXT, parent_task_id TEXT, created_at TEXT, updated_at TEXT,
      error TEXT, token_usage INTEGER)
events(id TEXT PK, task_id TEXT, kind TEXT, payload TEXT, created_at TEXT)
subscriptions(thread_id TEXT, worker_id TEXT, created_at TEXT, PRIMARY KEY(thread_id, worker_id))
memory(key TEXT PK, value TEXT, updated_at TEXT)   -- Router 的长期摘要
```

- 消息写库后再广播，保证「刷新/重启后可恢复」。
- `tasks.status` 状态机：`queued → running → done | failed | stopped`。
- 恢复策略：进程启动时把 `running` 任务标记为 `interrupted`，由 Watchdog/Router 决定重跑或告知用户。

---

## 6. 运行模型（单进程内的「分布式」）

MVP 不引入消息队列与容器编排，但**接口按可拆分的方式设计**：

- `TriggerQueue`：`asyncio.Queue`，Router 每轮用 `get_nowait()` 批量取出，实现文章中的 **Batching**。
- `AgentRuntime`：持有 Router 任务、Worker 池、Watchdog 任务，挂在 FastAPI `lifespan` 上。
- `Store`：抽象接口 `InMemoryStore` → `SqliteStore`，便于测试与未来换成 Postgres/Redis。
- LLM：`LLMClient` 抽象（`chat(messages, tools) -> stream`），生产用 OpenAI 兼容协议，测试用 `FakeLLM`。
- 后续把 Worker 拆到独立进程/机器时，只需把 `TriggerQueue` 换成 Redis Stream，Store 换成共享数据库。

---

## 7. 分阶段路线图

### P0 · 骨架与最小闭环（约 0.5–1 天）

- [x] `backend/agent/config.py`：`AGENT_ENABLED`、`AGENT_NAME`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`、并发/预算上限
- [x] `backend/agent/llm.py`：OpenAI 兼容客户端 + 流式；`FakeLLM` 用于测试
- [x] `backend/agent/filters.py`：`Trigger` 数据类 + FastPath（`@名字` / 私聊 / 忽略自身消息）
- [x] `backend/agent/router.py`：单常驻循环，直接回复或分派
- [x] `backend/main.py`：`lifespan` 启动/关闭 runtime；`chat` 消息命中 Trigger 时入队
- [x] 前端：`useChat` 解析 `agent.*`，房间内渲染 Agent 回复（含「思考中」状态）

**验收**：房间里 `@小深 你好`，3 秒内流式返回；普通聊天不触发；Agent 自己的消息不形成回环。

### P1 · Worker 与任务面板（约 1–2 天）

- [x] `worker.py`：独立消息上下文、工具循环、`start_task/stop_task`、超时与最大轮数
- [x] `registry.py`：`thread → worker` 订阅与直通
- [x] `context.py`：房间简短（≤100 字）/ 面板结构化两种输出规范
- [x] 前端：右侧 Agent 抽屉（对话 + 任务卡 + 停止按钮 + 折叠 trace）
- [x] 任务状态事件全链路：`queued → running → done/failed/stopped`

**验收**：同时发 3 个任务，互不阻塞、上下文不串；可单独停止；同一 Thread 的追问直接进入原 Worker。

### P2 · 持久化与链式召回（约 1 天）

- [ ] `store.py` + SQLite 建表与迁移
- [ ] 消息/任务/订阅落库；启动恢复未完成任务
- [ ] `context.py`：Inline 最近消息 + 关联 ID；超限 Spill
- [ ] 工具：`read_thread`、`read_message`、`read_task`（按 ID 逐跳展开）
- [ ] Agent 面板支持历史记录分页

**验收**：重启服务后历史仍在；Agent 能通过 2 跳以上找回旧任务上下文。

### P3 · 主动性与自愈（约 1–2 天）

- [ ] 过滤 SlowPath：LLM 判定「是否需要介入」，支持自然语言策略配置
- [ ] 投机执行：识别「疑似问题反馈」时后台预跑，确认后再交付
- [ ] `watchdog.py`：Worker 心跳/无进展/超时 → 取消或重启，并向 Router 报告
- [ ] `/health` 扩展：队列深度、运行中任务、最近异常
- [ ] 简单限流与预算：每用户每分钟 Trigger 数、每任务 token 上限

**验收**：注入一个死循环 Worker，Watchdog 能在 60 秒内收敛；群聊噪音不产生回复。

### P4 · 外部信道与安全（2–3 天，可选）

- [ ] `channels/github.py`：Issue/PR 评论作为 Trigger，结果回写评论
- [ ] `channels/im.py`：企业微信/飞书/Slack Webhook 适配
- [ ] 端侧 daemon 概念验证（BYOM）：命令执行与结果返回，不持有会话状态
- [ ] 安全：聊天内容标记为不可信、工具白名单、密钥隔离、审计日志、A2A 鉴权

---

## 8. 关键设计决策

| 决策 | 选择 | 理由 |
| --- | --- | --- |
| 进程模型 | 单进程 asyncio，多任务并发 | 当前规模够用，避免过早引入 MQ |
| 存储 | SQLite（WAL） | 零运维、可恢复；接口预留切换 |
| LLM 协议 | OpenAI 兼容（可指向 DeepSeek） | 换模型只改 base_url/model |
| 流式 | SSE/流式 chunk → WS `agent.delta` | 满足「高效」体感 |
| 工具 | 默认只读（读消息/读任务/时间/计算）；写文件与 shell 需显式开启 | 安全优先 |
| Agent 输出 | 只经 Router / channel 层 | 防止多 Worker 抢话 |
| 上下文 | Inline 最近 N 条 + 摘要 + 关联 ID，其余 Spill | 控制窗口与成本 |

---

## 9. 安全与成本

- **提示词注入**：所有聊天内容进入模型前包一层 `untrusted` 标记；工具参数需结构化校验；默认不给 shell。
- **密钥**：只从 `.env` / 环境变量读取，`.env` 加入 `.gitignore`，绝不下发前端。
- **成本**：Router 用轻量模型、Worker 用强模型；设置单任务最大轮数、token 预算、并发上限（默认 3）。
- **回环**：Agent 消息带 `role=agent`，FastPath 直接丢弃，避免自触发。
- **隐私**：私聊 Thread 只有本人可见；房间内 Agent 只读取公开消息。

---

## 10. 测试计划

- **单元**：Trigger 过滤规则、批处理合并、Thread 订阅路由、Worker 上下文隔离、Inline/Spill 截断。
- **集成**：`FakeLLM` + `TestClient.websocket_connect` 跑通「@ → 分派 → 流式 → done」。
- **回归**：现有 `test_chat.py` 的昵称/广播行为保持不变。
- **故障注入**：LLM 超时、Worker 抛错、客户端中途断开、服务重启。

---

## 11. 待确认

1. **模型与密钥**：默认按 DeepSeek（`https://api.deepseek.com`，`deepseek-chat`）设计，是否可行？
2. **首发范围**：建议先做 P0 + P1（可用的 Agent 入口 + 任务面板），P2 之后按需推进。
3. **Agent 可见性**：房间里是否始终显示「小深 在线」，还是仅被 @ 时出现？
4. **工具权限**：MVP 是否只做只读工具（不碰文件系统/命令）？
