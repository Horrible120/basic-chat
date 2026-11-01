from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi import WebSocket


@dataclass
class Client:
    user_id: str
    nickname: str
    socket: WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[str, Client] = {}

    @property
    def count(self) -> int:
        return len(self.connections)

    def members(self) -> list[dict[str, str]]:
        return [{"userId": client.user_id, "nickname": client.nickname} for client in self.connections.values()]

    def add(self, nickname: str, socket: WebSocket) -> Client:
        client = Client(str(uuid4()), nickname, socket)
        self.connections[client.user_id] = client
        return client

    def remove(self, user_id: str) -> None:
        self.connections.pop(user_id, None)

    async def send(self, client: Client, packet: dict) -> None:
        await client.socket.send_json(packet)

    async def send_to(self, user_id: str, packet: dict) -> bool:
        client = self.connections.get(user_id)
        if client is None:
            return False
        try:
            await client.socket.send_json(packet)
            return True
        except Exception:
            self.remove(user_id)
            return False

    async def broadcast(self, packet: dict) -> None:
        stale: list[str] = []
        for user_id, client in list(self.connections.items()):
            try:
                await client.socket.send_json(packet)
            except Exception:
                stale.append(user_id)
        for user_id in stale:
            self.remove(user_id)
