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

## WebSocket 协议

连接 `/ws?nickname=昵称`。客户端发送 `{ "type": "chat", "content": "消息" }`；服务端发送 `ready`、`chat`、`presence`、`error` 事件。昵称长度为 1–20，消息长度为 1–2000，均按纯文本处理。

