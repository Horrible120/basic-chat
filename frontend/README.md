# 聊天室智能体对接说明

## 当前实现

多人聊天室保留原有 WebSocket 通信。智能体默认名称为“小深”，在聊天中输入 `@小深` 加上问题，或点击输入框旁的 @ 按钮，可以向服务端发起房间内请求；智能体的房间回复由服务端发送，供在线成员查看。名称可由后端配置，具体操作见[项目 README](../README.md)。

后端实现了 Router 和 Worker、工具调用以及智能体事件。前端通过 `frontend/src/composables/useChat.js` 处理智能体回复、任务状态和执行记录；任务面板使用这些事件展示工具步骤。没有配置模型密钥时，后端使用演示模式，返回配置提示；这不证明真实模型或工具调用可用。

当前仅提供进程内会话与任务状态，服务重启后不保留。具体支持的工具及其配置以[项目 README](../README.md)和后端实现为准。

## 接口与责任

聊天继续使用原有 `/ws?nickname=昵称`。智能体的 `agent.delta`、`agent.state`、`agent.trace`、`agent.done` 和 `agent.error` 等事件以[项目 README](../README.md)和后端实现为准；前端负责展示，后端负责模型请求、工具执行及房间广播。模型密钥只应配置在后端环境中。

## 后续联调

- 两个用户同时在线时，确认 @ 智能体后的房间回复两人均可看到，普通聊天保持正常。
- 检查任务执行、工具步骤、失败和停止状态；分别验证演示模式与实际配置的模型。
- 检查并发提问、断线重连以及手机和桌面布局。

前端构建成功或离线测试通过不代表真实模型和外部服务已验证。

## 当前前后端 API 格式

以下按当前仓库实现整理，字段值均为示例。主要通信方式是 WebSocket，每条消息都是一个 JSON 对象。生产环境应使用 `wss://`，并对昵称进行 URL 编码。

### 连接与健康检查

```text
WebSocket: ws://localhost:8000/ws?nickname=%E5%B0%8F%E9%9B%A8
HTTP:      GET /health
```

开发时通过 Vite 的 `/ws` 代理访问后端。昵称去除首尾空格后必须为 1–20 字符，不能占用智能体名称或 `agent`；不合法时服务端发出 `error` 并以 1008 关闭连接。

`GET /health` 返回示例：

```json
{"status":"ok","online":1,"agent":{"name":"小深","online":true,"demo":true,"allowWrite":true,"maxWorkers":3}}
```

### 前端发送给后端

```json
{"type":"chat","content":"大家好"}
{"type":"chat","content":"@小深 你好"}
{"type":"agent.dm","content":"帮我看看项目结构"}
{"type":"agent.stop","taskId":"task_123"}
```

`chat` 是公开房间消息；其中包含当前智能体名称（默认 `@小深`）会触发智能体。`agent.dm` 是私聊；`agent.stop` 用于停止自己发起的任务。消息内容去除首尾空格后必须为 1–2000 字符，停止任务必须有非空 `taskId`。

### 后端发送给前端

连接成功后先收到 `ready`，之后加入或离开会收到 `presence`。两种事件的 `members` 均是当前在线成员快照：

```json
{"type":"ready","userId":"用户ID","nickname":"小雨","onlineCount":1,"members":[{"userId":"用户ID","nickname":"小雨"}],"agent":{"name":"小深","online":true,"demo":true,"allowWrite":true,"maxWorkers":3}}
{"type":"presence","onlineCount":1,"members":[{"userId":"用户ID","nickname":"小雨"}]}
```

房间消息广播给在线成员。普通消息和智能体最终回复都带有消息身份信息；`threadId`、`channel` 用于区分房间与私聊。

```json
{"type":"chat","id":"消息ID","messageId":"消息ID","threadId":"room:main","channel":"room","role":"user","nickname":"小雨","userId":"用户ID","content":"@小深 你好","timestamp":"2026-11-01T08:00:00+00:00","isAgent":false}
{"type":"agent.done","taskId":null,"id":"回复ID","messageId":"回复ID","threadId":"room:main","channel":"room","role":"agent","nickname":"小深","userId":"agent","content":"你好！","timestamp":"2026-11-01T08:00:01+00:00","isAgent":true}
```

智能体的流式文本与任务事件：

```json
{"type":"agent.delta","threadId":"room:main","messageId":"回复ID","channel":"room","taskId":null,"content":"你好"}
{"type":"agent.delta","threadId":"room:main","messageId":"回复ID","channel":"room","taskId":"task_123","scope":"task","content":"执行进度"}
{"type":"agent.state","taskId":"task_123","threadId":"room:main","channel":"room","ownerId":"用户ID","title":"查看项目","status":"running","steps":1,"result":"","error":"","createdAt":"2026-11-01T08:00:00+00:00","updatedAt":"2026-11-01T08:00:01+00:00"}
{"type":"agent.trace","taskId":"task_123","step":"工具步骤","detail":"执行详情","timestamp":"2026-11-01T08:00:01+00:00"}
{"type":"agent.error","threadId":"room:main","channel":"room","message":"智能体处理失败"}
{"type":"error","message":"消息不能为空"}
```

`agent.delta` 的 `content` 是增量，应按 `messageId` 拼接；`agent.done` 包含完整最终内容。任务状态可能是 `queued`、`running`、`done`、`failed` 或 `stopped`。`agent.trace` 是任务步骤记录，任务状态、工具步骤和任务增量发送给任务发起者；房间频道的最终回复广播给在线成员。部分 `agent.error` 只有 `type` 和 `message`，前端不要假定其他字段总是存在。

私聊还会收到 `agent.message`（发送的私聊消息回显，字段与上面的消息身份信息相同）和 `agent.history`：

```json
{"type":"agent.history","threadId":"dm:用户ID","messages":[{"id":"消息ID","role":"user","content":"你好","timestamp":"2026-11-01T08:00:00+00:00"}]}
```

服务端当前在进程内保存聊天与任务数据；私聊按连接用户 ID 区分，刷新或重连后的历史不保证恢复。真实模型和真实工具的可用性需要单独联调验证。

### @ 聊天成员

在输入框输入 `@` 或点击 @ 按钮可选择在线成员或智能体，继续输入可筛选昵称；也可以点击消息中的昵称或手动输入。前端根据 `ready` 和 `presence` 中的 `members` 快照维护名单。@ 内容仍是普通公开文本，没有专门通知机制，重复昵称无法作为唯一身份区分。
