from __future__ import annotations

import asyncio
import time
from collections import deque

from .config import AgentConfig
from .filters import TriggerBuilder
from .llm import BaseLLM, build_llm
from .registry import WorkerRegistry
from .router import Router
from .store import AgentStore
from .types import AGENT_USER_ID, ROOM_THREAD, Message, Task, Trigger, dm_thread, new_id, now_iso
from .worker import Worker


class AgentRuntime:
    """Super-agent 的进程内运行时：Router + Worker 池 + 订阅表。"""

    def __init__(
        self,
        config: AgentConfig,
        manager,
        *,
        store: AgentStore | None = None,
        llm: BaseLLM | None = None,
    ) -> None:
        self.config = config
        self.manager = manager
        self.store = store or AgentStore()
        self.llm = llm or build_llm(config)
        self.filter = TriggerBuilder(config.name)
        self.registry = WorkerRegistry()
        self.queue: asyncio.Queue[Trigger] = asyncio.Queue(maxsize=100)
        self.router = Router(self)

        self._router_task: asyncio.Task | None = None
        self._workers: dict[str, asyncio.Task] = {}
        self._sessions: dict[str, Worker] = {}
        self._semaphore = asyncio.Semaphore(config.max_workers)
        self._rate: dict[str, deque[float]] = {}
        self._started = False

    # ---------- 生命周期 ----------
    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._router_task = asyncio.create_task(self.router.run(), name="agent-router")

    async def stop(self) -> None:
        self._started = False
        if self._router_task is not None:
            self._router_task.cancel()
            self._router_task = None
        jobs = list(self._workers.values())
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        await self.llm.aclose()

    def public_info(self) -> dict:
        return {
            "name": self.config.name,
            "online": self._started,
            "demo": self.llm.demo,
            "allowWrite": self.config.allow_write,
            "maxWorkers": self.config.max_workers,
        }

    # ---------- 入口 ----------
    def record_room_message(
        self,
        *,
        user_id: str,
        nickname: str,
        content: str,
        message_id: str,
        created_at: str | None = None,
    ) -> Message:
        return self.store.add_message(
            thread_id=ROOM_THREAD,
            channel="room",
            role="user",
            nickname=nickname,
            content=content,
            user_id=user_id,
            message_id=message_id,
            created_at=created_at,
        )

    async def on_room_message(self, client, content: str, message_id: str) -> None:
        trigger = self.filter.room(client.user_id, client.nickname, content, message_id)
        if trigger is None:
            return
        if not self._allow(client.user_id):
            await self._notify_user(client, "触发太频繁了，稍等一会儿再试。")
            return
        await self._enqueue(trigger)

    async def on_dm(self, client, content: str) -> None:
        message = self.store.add_message(
            thread_id=dm_thread(client.user_id),
            channel="dm",
            role="user",
            nickname=client.nickname,
            content=content,
            user_id=client.user_id,
            message_id=new_id("msg"),
        )
        await self.manager.send_to(client.user_id, {"type": "agent.message", **message.as_packet()})

        trigger = self.filter.direct(client.user_id, client.nickname, content)
        if trigger is None:
            return
        if not self._allow(client.user_id):
            await self._notify_user(client, "触发太频繁了，稍等一会儿再试。")
            return
        await self._enqueue(trigger)

    async def send_history(self, client) -> None:
        messages = self.store.thread_messages(dm_thread(client.user_id), limit=50)
        await self.manager.send_to(
            client.user_id,
            {
                "type": "agent.history",
                "threadId": dm_thread(client.user_id),
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "timestamp": message.created_at,
                    }
                    for message in messages
                ],
            },
        )

    async def stop_task(self, task_id: str, client) -> None:
        task = self.store.get_task(task_id)
        if task is None:
            await self._notify_user(client, "找不到这个任务。")
            return
        if task.owner_id != client.user_id:
            await self._notify_user(client, "只能停止自己发起的任务。")
            return
        if task.status not in {"queued", "running"}:
            return
        self.store.update_task(task, status="stopped")
        job = self._workers.get(task.id)
        if job is not None and not job.done():
            job.cancel()
        else:
            await self.emit_state(task)

    # ---------- 队列与限流 ----------
    async def _enqueue(self, trigger: Trigger) -> None:
        try:
            self.queue.put_nowait(trigger)
        except asyncio.QueueFull:
            await self.notify(trigger, "智能体当前排队的任务太多了，请稍后再试。")

    def _allow(self, user_id: str) -> bool:
        now = time.monotonic()
        bucket = self._rate.setdefault(user_id, deque())
        while bucket and now - bucket[0] > self.config.rate_window:
            bucket.popleft()
        if len(bucket) >= self.config.rate_limit:
            return False
        bucket.append(now)
        return True

    # ---------- 对外输出 ----------
    async def emit_delta(self, trigger: Trigger, message_id: str, text: str) -> None:
        packet = {
            "type": "agent.delta",
            "threadId": trigger.thread_id,
            "messageId": message_id,
            "channel": trigger.channel,
            "taskId": None,
            "content": text,
        }
        await self._emit(trigger.channel, trigger.owner_id, packet)

    async def emit_reply(self, trigger: Trigger, message_id: str, content: str) -> None:
        message = self.store.add_message(
            thread_id=trigger.thread_id,
            channel=trigger.channel,
            role="agent",
            nickname=self.config.name,
            content=content,
            user_id=AGENT_USER_ID,
            message_id=message_id,
        )
        packet = {"type": "agent.done", "taskId": None, **message.as_packet()}
        await self._emit(trigger.channel, trigger.owner_id, packet)

    async def emit_task_delta(self, worker: Worker, text: str) -> None:
        task = worker.task
        await self.manager.send_to(
            task.owner_id,
            {
                "type": "agent.delta",
                "threadId": task.thread_id,
                "messageId": worker.message_id,
                "channel": task.channel,
                "taskId": task.id,
                "scope": "task",
                "content": text,
            },
        )

    async def emit_trace(self, task: Task, step: str, detail: str) -> None:
        await self.manager.send_to(
            task.owner_id,
            {
                "type": "agent.trace",
                "taskId": task.id,
                "step": step,
                "detail": detail,
                "timestamp": now_iso(),
            },
        )

    async def emit_state(self, task: Task) -> None:
        packet = {"type": "agent.state", **task.public()}
        await self.manager.send_to(task.owner_id, packet)

    async def notify(self, trigger: Trigger, message: str) -> None:
        await self._emit(
            trigger.channel,
            trigger.owner_id,
            {
                "type": "agent.error",
                "threadId": trigger.thread_id,
                "channel": trigger.channel,
                "message": message,
            },
        )

    async def _notify_user(self, client, message: str) -> None:
        await self.manager.send_to(client.user_id, {"type": "agent.error", "message": message})

    async def _emit(self, channel: str, owner_id: str, packet: dict) -> None:
        if channel == "room":
            await self.manager.broadcast(packet)
        else:
            await self.manager.send_to(owner_id, packet)

    # ---------- 任务 ----------
    async def start_task(self, trigger: Trigger, title: str, instruction: str) -> Task:
        task = self.store.create_task(
            thread_id=trigger.thread_id,
            channel=trigger.channel,
            owner_id=trigger.owner_id,
            title=title,
            instruction=instruction,
        )
        worker = Worker(self.config, self.llm, self.store, self, task, trigger)
        self.registry.subscribe(task.thread_id, worker)
        job = asyncio.create_task(self._run_worker(worker), name=f"agent-worker:{task.id}")
        self._workers[task.id] = job
        self._sessions[task.id] = worker
        await self.emit_state(task)
        return task

    async def finish_task(self, task: Task, content: str) -> None:
        worker = self._sessions.get(task.id)
        message_id = worker.message_id if worker is not None else new_id("msg")
        self.store.update_task(task, status="done", result=content, error="")
        await self._deliver(task, content, message_id)
        await self.emit_state(task)

    async def fail_task(self, task: Task, error: str) -> None:
        worker = self._sessions.get(task.id)
        message_id = worker.message_id if worker is not None else new_id("msg")
        self.store.update_task(task, status="failed", error=error[:500])
        await self._deliver(task, f"任务失败：{error[:300]}", message_id)
        await self.emit_state(task)

    async def _deliver(self, task: Task, content: str, message_id: str) -> None:
        message = self.store.add_message(
            thread_id=task.thread_id,
            channel=task.channel,
            role="agent",
            nickname=self.config.name,
            content=content,
            user_id=AGENT_USER_ID,
            message_id=message_id,
        )
        await self._emit(task.channel, task.owner_id, {"type": "agent.done", "taskId": task.id, **message.as_packet()})

    async def _run_worker(self, worker: Worker) -> None:
        task = worker.task
        try:
            async with self._semaphore:
                if task.status == "stopped":
                    await self.emit_state(task)
                    return
                self.store.update_task(task, status="running")
                await self.emit_state(task)
                await worker.run()
        except asyncio.CancelledError:
            if task.status != "stopped":
                self.store.update_task(task, status="stopped")
            await self.emit_state(task)
            await self._deliver(task, "任务已停止。", worker.message_id)
        except Exception as exc:
            await self.fail_task(task, str(exc))
        finally:
            self.registry.unsubscribe(task.thread_id, worker)
            self._workers.pop(task.id, None)
            self._sessions.pop(task.id, None)
