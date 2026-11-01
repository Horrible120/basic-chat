from __future__ import annotations

import asyncio

from .context import build_worker_messages
from .llm import LLMResult
from .store import AgentStore
from .tools import execute_tool, tool_schemas
from .types import Task, Trigger, now_iso


class Worker:
    """上下文隔离的执行会话：只处理一个任务，不直接对用户说话。"""

    def __init__(
        self,
        config,
        llm,
        store: AgentStore,
        runtime,
        task: Task,
        trigger: Trigger,
    ) -> None:
        self.config = config
        self.llm = llm
        self.store = store
        self.runtime = runtime
        self.task = task
        self.trigger = trigger
        self.message_id = f"msg_{task.id}_out"
        self.inbox: list[str] = []
        self.finished = False
        self._schemas = tool_schemas(config.allow_write)

    def deliver(self, trigger: Trigger) -> bool:
        if self.finished:
            return False
        self.inbox.append(f"{trigger.owner_name}: {trigger.content}")
        return True

    async def run(self) -> None:
        messages = build_worker_messages(self.config, self.store, self.task, self.trigger)
        try:
            for step in range(1, self.config.max_steps + 1):
                self.store.update_task(self.task, steps=step)
                if self.inbox:
                    supplement = "\n".join(self.inbox)
                    self.inbox.clear()
                    messages.append({"role": "user", "content": f"用户补充了新的消息，请一并考虑：\n{supplement}"})

                result = LLMResult()
                async for event in self.llm.stream(
                    messages,
                    model=self.config.worker_model,
                    tools=self._schemas,
                    temperature=self.config.temperature,
                    max_tokens=self.config.worker_max_tokens,
                ):
                    if event.kind == "delta" and event.text:
                        await self.runtime.emit_task_delta(self, event.text)
                    elif event.kind == "final" and event.result is not None:
                        result = event.result

                if result.tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": result.content or "",
                            "tool_calls": [
                                {
                                    "id": call.id,
                                    "type": "function",
                                    "function": {"name": call.name, "arguments": call.arguments},
                                }
                                for call in result.tool_calls
                            ],
                        }
                    )
                    for call in result.tool_calls:
                        args = call.parsed()
                        await self.runtime.emit_trace(self.task, f"tool:{call.name}", _brief(args))
                        output = await execute_tool(
                            call.name,
                            args,
                            store=self.store,
                            task=self.task,
                            allow_write=self.config.allow_write,
                        )
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
                        self.store.update_task(self.task, updated_at=now_iso())
                    continue

                content = (result.content or "").strip() or "（任务没有产生文本结果）"
                await self.runtime.finish_task(self.task, content)
                return

            await self.runtime.fail_task(self.task, f"超过最大步数（{self.config.max_steps}）")
        finally:
            self.finished = True


def _brief(args: dict) -> str:
    text = ", ".join(f"{key}={str(value)[:60]}" for key, value in args.items())
    return text[:160] or "（无参数）"
