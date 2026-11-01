from __future__ import annotations

from collections import deque

from .types import Message, Task, new_id, now_iso


class AgentStore:
    """进程内存储。P2 阶段会替换为 SQLite 实现，接口保持不变。"""

    def __init__(self, max_messages: int = 2000, max_thread_messages: int = 400) -> None:
        self._messages: deque[Message] = deque(maxlen=max_messages)
        self._by_id: dict[str, Message] = {}
        self._threads: dict[str, deque[str]] = {}
        self._max_thread_messages = max_thread_messages
        self.tasks: dict[str, Task] = {}

    def add_message(
        self,
        *,
        thread_id: str,
        channel: str,
        role: str,
        nickname: str,
        content: str,
        user_id: str = "",
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> Message:
        message = Message(
            id=message_id or new_id("msg"),
            thread_id=thread_id,
            channel=channel,
            role=role,
            nickname=nickname,
            content=content,
            created_at=created_at or now_iso(),
            user_id=user_id,
        )
        self._messages.append(message)
        self._by_id[message.id] = message
        thread = self._threads.setdefault(thread_id, deque(maxlen=self._max_thread_messages))
        thread.append(message.id)
        return message

    def get_message(self, message_id: str) -> Message | None:
        return self._by_id.get(message_id)

    def thread_messages(self, thread_id: str, limit: int = 20) -> list[Message]:
        ids = self._threads.get(thread_id)
        if not ids:
            return []
        selected = list(ids)[-max(1, limit):]
        return [self._by_id[item] for item in selected if item in self._by_id]

    def create_task(
        self,
        *,
        thread_id: str,
        channel: str,
        owner_id: str,
        title: str,
        instruction: str,
        complexity: str = "light",
    ) -> Task:
        task = Task(
            id=new_id("task"),
            thread_id=thread_id,
            channel=channel,
            owner_id=owner_id,
            title=title[:80],
            instruction=instruction[:4000],
            complexity="heavy" if complexity == "heavy" else "light",
        )
        self.tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def update_task(self, task: Task, **fields) -> Task:
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = now_iso()
        return task
