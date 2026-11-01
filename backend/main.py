from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .connection_manager import ConnectionManager
from .schemas import ClientPacket, clean_text

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
app = FastAPI(title="Basic Chat")
manager = ConnectionManager()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "online": manager.count})


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
    client = manager.add(name, websocket)
    try:
        await manager.send(client, {"type": "ready", "userId": client.user_id, "nickname": client.nickname, "onlineCount": manager.count})
        await manager.broadcast({"type": "presence", "onlineCount": manager.count})
        while True:
            try:
                raw = await websocket.receive_text()
                packet = ClientPacket.model_validate_json(raw)
                if packet.type != "chat":
                    raise ValueError("不支持的消息类型")
            except WebSocketDisconnect:
                break
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                message = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
                await manager.send(client, {"type": "error", "message": message})
                continue
            await manager.broadcast({"type": "chat", "id": str(uuid4()), "userId": client.user_id, "nickname": client.nickname, "content": packet.content, "timestamp": datetime.now(timezone.utc).isoformat()})
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
