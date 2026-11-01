from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .agent import AgentConfig, AgentRuntime
from .connection_manager import ConnectionManager
from .schemas import ClientPacket, clean_text

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"

config = AgentConfig.from_env()
manager = ConnectionManager()
runtime = AgentRuntime(config, manager)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(title="Basic Chat", lifespan=lifespan)


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return exc.errors()[0]["msg"].removeprefix("Value error, ")
    return str(exc)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "online": manager.count, "agent": runtime.public_info()})


@app.websocket("/ws")
async def websocket_chat(websocket: WebSocket, nickname: str = Query(...)) -> None:
    try:
        name = clean_text(nickname, max_length=20, label="昵称")
    except ValueError as exc:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1008)
        return

    await websocket.accept()
    if name == config.name or name.lower() == "agent":
        await websocket.send_json({"type": "error", "message": f"昵称「{name}」已被智能体占用，请换一个。"})
        await websocket.close(code=1008)
        return

    client = manager.add(name, websocket)
    try:
        await manager.send(
            client,
            {
                "type": "ready",
                "userId": client.user_id,
                "nickname": client.nickname,
                "onlineCount": manager.count,
                "agent": runtime.public_info(),
            },
        )
        await manager.broadcast({"type": "presence", "onlineCount": manager.count})
        await runtime.send_history(client)

        while True:
            try:
                raw = await websocket.receive_text()
                packet = ClientPacket.model_validate_json(raw)
            except WebSocketDisconnect:
                break
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                await manager.send(client, {"type": "error", "message": _error_message(exc)})
                continue

            if packet.type == "chat":
                timestamp = datetime.now(timezone.utc).isoformat()
                message = runtime.record_room_message(
                    user_id=client.user_id,
                    nickname=client.nickname,
                    content=packet.content,
                    message_id=str(uuid4()),
                    created_at=timestamp,
                )
                await manager.broadcast({"type": "chat", **message.as_packet()})
                await runtime.on_room_message(client, packet.content, message.id)
            elif packet.type == "agent.dm":
                await runtime.on_dm(client, packet.content)
            elif packet.type == "agent.stop":
                await runtime.stop_task(packet.taskId or "", client)
    finally:
        manager.remove(client.user_id)
        await manager.broadcast({"type": "presence", "onlineCount": manager.count})


if DIST.exists():
    assets = DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(DIST / "index.html")
else:

    @app.get("/")
    async def index() -> JSONResponse:
        return JSONResponse({"message": "前端尚未构建，请运行 pnpm --dir frontend build"}, status_code=503)
