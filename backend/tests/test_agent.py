from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.agent.config import AgentConfig, ROOT
from backend.agent.context import build_router_messages
from backend.agent.filters import TriggerBuilder
from backend.agent.llm import BaseLLM, LLMEvent, LLMResult, ToolCall
from backend.agent.runtime import AgentRuntime
from backend.agent.store import AgentStore
from backend.agent.tools import execute_tool, tool_schemas
from backend.agent.types import Trigger


class ScriptedLLM(BaseLLM):
    def __init__(self, results: list[LLMResult]) -> None:
        self.results = list(results)
        self.calls: list[dict] = []

    async def stream(self, messages, *, model, tools=None, temperature=0.3, max_tokens=1024):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
        result = self.results.pop(0) if self.results else LLMResult(content="好的。")
        for index in range(0, len(result.content), 6):
            yield LLMEvent("delta", text=result.content[index:index + 6])
        yield LLMEvent("final", result=result)


class SlowLLM(BaseLLM):
    async def stream(self, messages, *, model, tools=None, temperature=0.3, max_tokens=1024):
        await asyncio.sleep(5)
        yield LLMEvent("final", result=LLMResult(content="太慢了"))


class FakeManager:
    def __init__(self) -> None:
        self.broadcasted: list[dict] = []
        self.sent: list[tuple[str, dict]] = []

    async def broadcast(self, packet: dict) -> None:
        self.broadcasted.append(packet)

    async def send_to(self, user_id: str, packet: dict) -> bool:
        self.sent.append((user_id, packet))
        return True


class FakeClient:
    def __init__(self, user_id: str = "u1", nickname: str = "小雨") -> None:
        self.user_id = user_id
        self.nickname = nickname


def test_room_trigger_requires_mention():
    builder = TriggerBuilder("小深")
    assert builder.room("u1", "小雨", "大家好", "m1") is None
    trigger = builder.room("u1", "小雨", "@小深 帮我看看", "m1")
    assert trigger is not None
    assert trigger.content == "帮我看看"
    assert trigger.thread_id == "room:main"
    assert builder.room("agent", "小深", "@小深 自问自答", "m2") is None


def test_direct_trigger_and_thread():
    builder = TriggerBuilder("小深")
    trigger = builder.direct("u9", "小雨", "  你好  ")
    assert trigger is not None
    assert trigger.thread_id == "dm:u9"
    assert trigger.channel == "dm"
    assert trigger.content == "你好"


def test_router_context_excludes_current_message():
    config = AgentConfig(name="小深")
    store = AgentStore()
    store.add_message(thread_id="room:main", channel="room", role="user", nickname="小雨", content="旧消息", message_id="m1")
    store.add_message(thread_id="room:main", channel="room", role="user", nickname="小雨", content="@小深 新消息", message_id="m2")
    trigger = TriggerBuilder("小深").room("u1", "小雨", "@小深 新消息", "m2")
    messages = build_router_messages(config, store, trigger)
    assert "旧消息" in messages[1]["content"]
    assert "新消息" in messages[1]["content"]
    assert "m2] 小雨" not in messages[1]["content"]


def test_workspace_guard_and_read_write(tmp_path: Path):
    store = AgentStore()
    task = store.create_task(thread_id="room:main", channel="room", owner_id="u1", title="t", instruction="i")

    outside = asyncio.run(execute_tool("read_file", {"path": "../../secret.txt"}, store=store, task=task))
    assert "error" in json.loads(outside)

    blocked = asyncio.run(execute_tool("read_file", {"path": ".env"}, store=store, task=task))
    assert "error" in json.loads(blocked)

    target = ROOT / "backend" / "tests" / "_tmp_agent_file.txt"
    try:
        written = asyncio.run(
            execute_tool("write_file", {"path": "backend/tests/_tmp_agent_file.txt", "content": "你好 agent"},
                         store=store, task=task, allow_write=True)
        )
        assert json.loads(written)["ok"] is True
        read = asyncio.run(execute_tool("read_file", {"path": "backend/tests/_tmp_agent_file.txt"}, store=store, task=task))
        assert json.loads(read)["content"] == "你好 agent"
    finally:
        target.unlink(missing_ok=True)


def test_tool_schemas_respect_write_flag():
    names = {item["function"]["name"] for item in tool_schemas(allow_write=False)}
    assert "write_file" not in names
    assert "read_file" in names


def test_router_dispatches_and_worker_finishes():
    async def scenario() -> tuple[AgentRuntime, FakeManager, ScriptedLLM]:
        llm = ScriptedLLM(
            [
                LLMResult(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call_1",
                            name="dispatch_task",
                            arguments=json.dumps({"title": "查看结构", "instruction": "读一下 README"}),
                        )
                    ],
                ),
                LLMResult(content="README 已看完，没问题。"),
            ]
        )
        manager = FakeManager()
        runtime = AgentRuntime(AgentConfig(name="小深", max_workers=2), manager, llm=llm)
        await runtime.start()
        client = FakeClient()
        message = runtime.record_room_message(
            user_id="u1", nickname="小雨", content="@小深 看一下项目", message_id="m1"
        )
        await runtime.on_room_message(client, message.content, message.id)
        for _ in range(300):
            tasks = list(runtime.store.tasks.values())
            if tasks and tasks[0].status in {"done", "failed", "stopped"}:
                break
            await asyncio.sleep(0.01)
        snapshot = (
            [(task.status, task.result) for task in runtime.store.tasks.values()],
            list(manager.broadcasted),
            len(llm.calls),
            bool(llm.calls and llm.calls[-1]["tools"]),
        )
        await runtime.stop()
        return snapshot

    task_results, broadcasted, call_count, worker_tools = asyncio.run(scenario())
    assert len(task_results) == 1
    assert task_results[0] == ("done", "README 已看完，没问题。")

    ack = [packet for packet in broadcasted if packet["type"] == "agent.done"]
    assert any("收到" in packet["content"] for packet in ack)
    assert any(packet["content"] == "README 已看完，没问题。" for packet in ack)
    assert call_count == 2
    assert worker_tools is True


def test_router_replies_directly_without_task():
    async def scenario():
        llm = ScriptedLLM([LLMResult(content="你好呀。")])
        manager = FakeManager()
        runtime = AgentRuntime(AgentConfig(name="小深"), manager, llm=llm)
        await runtime.start()
        client = FakeClient()
        message = runtime.record_room_message(user_id="u1", nickname="小雨", content="@小深 你好", message_id="m1")
        await runtime.on_room_message(client, message.content, message.id)
        for _ in range(100):
            if any(packet["type"] == "agent.done" for packet in manager.broadcasted):
                break
            await asyncio.sleep(0.01)
        replies = [packet for packet in manager.broadcasted if packet["type"] == "agent.done"]
        has_tasks = bool(runtime.store.tasks)
        await runtime.stop()
        return replies, has_tasks

    replies, has_tasks = asyncio.run(scenario())
    assert replies and replies[-1]["content"] == "你好呀。"
    assert not has_tasks


def test_stop_running_task():
    async def scenario():
        manager = FakeManager()
        runtime = AgentRuntime(AgentConfig(name="小深"), manager, llm=SlowLLM())
        trigger = Trigger(
            id="t1", thread_id="room:main", channel="room", owner_id="u1",
            owner_name="小雨", content="慢任务",
        )
        task = await runtime.start_task(trigger, "慢任务", "慢慢来")
        for _ in range(100):
            if task.status == "running":
                break
            await asyncio.sleep(0.01)
        await runtime.stop_task(task.id, FakeClient())
        for _ in range(200):
            packets = [packet for _, packet in manager.sent] + list(manager.broadcasted)
            if any(packet.get("type") == "agent.done" and "停止" in packet.get("content", "") for packet in packets):
                break
            await asyncio.sleep(0.01)
        snapshot = (task.status, [packet for _, packet in manager.sent] + list(manager.broadcasted))
        await runtime.stop()
        return snapshot

    status, packets = asyncio.run(scenario())
    assert status == "stopped"
    assert any(packet.get("type") == "agent.done" and "停止" in packet.get("content", "") for packet in packets)
    assert any(packet.get("type") == "agent.state" and packet.get("status") == "stopped" for packet in packets)
