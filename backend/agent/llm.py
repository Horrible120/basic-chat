from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str

    def parsed(self) -> dict:
        try:
            value = json.loads(self.arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


@dataclass(slots=True)
class LLMResult:
    content: str = ""
    reasoning: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(slots=True)
class LLMEvent:
    kind: str  # delta | reasoning | final
    text: str = ""
    result: LLMResult | None = None


class LLMError(RuntimeError):
    pass


class BaseLLM:
    demo = False

    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[LLMEvent]:
        raise NotImplementedError

    async def aclose(self) -> None:
        return None


class OpenAICompatibleLLM(BaseLLM):
    """OpenAI 兼容的流式客户端，默认指向 DeepSeek。"""

    def __init__(self, base_url: str, api_key: str, timeout: float = 180.0) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=self._timeout, write=30.0, pool=10.0)
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[LLMEvent]:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "max_tokens": max_tokens,
        }
        if thinking:
            payload["thinking"] = {"type": thinking}
        if reasoning_effort and thinking != "disabled":
            payload["reasoning_effort"] = reasoning_effort
        if thinking != "enabled":
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        content: list[str] = []
        reasoning_parts: list[str] = []
        calls: dict[int, dict] = {}
        try:
            async with self._get_client().stream("POST", self._url, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise LLMError(f"模型接口返回 {response.status_code}: {body[:300]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data:
                        continue
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if isinstance(reasoning, str) and reasoning:
                        reasoning_parts.append(reasoning)
                        yield LLMEvent("reasoning", text=reasoning)
                    text = delta.get("content")
                    if text:
                        content.append(text)
                        yield LLMEvent("delta", text=text)
                    for part in delta.get("tool_calls") or []:
                        index = int(part.get("index", 0) or 0)
                        slot = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                        if part.get("id"):
                            slot["id"] = part["id"]
                        function = part.get("function") or {}
                        if function.get("name"):
                            slot["name"] = function["name"]
                        if function.get("arguments"):
                            slot["arguments"] += function["arguments"]
        except httpx.HTTPError as exc:
            raise LLMError(f"调用模型失败：{exc}") from exc

        tool_calls = [
            ToolCall(id=slot["id"] or f"call_{index}", name=slot["name"], arguments=slot["arguments"] or "{}")
            for index, slot in sorted(calls.items())
            if slot["name"]
        ]
        yield LLMEvent(
            "final",
            result=LLMResult(
                content="".join(content),
                reasoning="".join(reasoning_parts),
                tool_calls=tool_calls,
            ),
        )


class EchoLLM(BaseLLM):
    """未配置密钥时的演示模式，保证前端链路可跑通。"""

    demo = True

    async def stream(
        self,
        messages: list[dict],
        *,
        model: str,
        tools: list[dict] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        thinking: str | None = None,
        reasoning_effort: str | None = None,
    ) -> AsyncIterator[LLMEvent]:
        text = "（演示模式）还没有配置 LLM_API_KEY。请在项目根目录创建 .env 并填写后重启服务，我就能真正干活了。"
        for index in range(0, len(text), 12):
            yield LLMEvent("delta", text=text[index:index + 12])
        yield LLMEvent("final", result=LLMResult(content=text))


def build_llm(config) -> BaseLLM:
    if config.demo_mode:
        return EchoLLM()
    return OpenAICompatibleLLM(config.base_url, config.api_key, config.request_timeout)
