from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from .config import ROOT


class DshError(RuntimeError):
    pass


@dataclass(slots=True)
class DshEvent:
    kind: str  # text | thinking | tool_call | tool_result | status | final
    text: str = ""
    name: str = ""
    detail: str = ""


@dataclass(slots=True)
class DshResult:
    content: str
    session_id: str = ""
    exit_code: int = 0


DshListener = Callable[[DshEvent], Awaitable[None]]


class DshBackend:
    """通过 `dsh --profile headless --json` 驱动 DeepSeek Harness 执行任务。"""

    def __init__(self, config) -> None:
        self.config = config
        self._resolved: str | None = None
        self._checked = False

    def available(self) -> bool:
        if not self.config.dsh_enabled:
            return False
        return self._resolve() is not None

    def _resolve(self) -> str | None:
        if self._checked:
            return self._resolved
        self._checked = True
        command = self.config.dsh_command.strip() or "dsh"
        candidate = Path(command)
        if candidate.is_file():
            self._resolved = str(candidate.resolve())
            return self._resolved
        found = shutil.which(command)
        if found:
            self._resolved = found
            return self._resolved
        if os.name == "nt" and command.lower() == "dsh":
            appdata = os.getenv("APPDATA")
            program_files = os.getenv("ProgramFiles", r"C:\Program Files")
            for path in (
                Path(appdata) / "npm" / "dsh.cmd" if appdata else None,
                Path(program_files) / "nodejs" / "dsh.cmd",
            ):
                if path is not None and path.is_file():
                    self._resolved = str(path)
                    return self._resolved
        return None

    def _argv(self, executable: str, args: list[str]) -> list[str]:
        if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
            return ["cmd.exe", "/c", executable, *args]
        return [executable, *args]

    async def run(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        on_event: DshListener | None = None,
        cwd: str | Path | None = None,
        model: str | None = None,
    ) -> DshResult:
        executable = self._resolve()
        if executable is None:
            raise DshError("未找到 dsh 命令，请先安装 DeepSeek Harness 或设置 HARNESS_COMMAND。")

        patch_path = self._model_patch(model) if model else None
        args = ["--profile", self.config.dsh_profile]
        if patch_path is not None:
            args += ["--patch", str(patch_path)]
        args.append("--json")
        if self.config.dsh_extra_args:
            args += [part.strip("\"'") for part in shlex.split(self.config.dsh_extra_args, posix=os.name != "nt")]
        if session_id:
            args += ["--session-id", session_id]
        args.append("-")

        environment = os.environ.copy()
        if os.name == "nt":
            extra = [
                Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "nodejs",
                Path(os.getenv("APPDATA", "")) / "npm",
            ]
            prefix = os.pathsep.join(str(item) for item in extra if item.is_dir())
            if prefix:
                environment["PATH"] = prefix + os.pathsep + environment.get("PATH", "")
        if self.config.api_key:
            environment["DEEPSEEK_API_KEY"] = self.config.api_key
        if self.config.dsh_base_url:
            environment["DEEPSEEK_BASE_URL"] = self.config.dsh_base_url
        if self.config.dsh_home:
            environment["DSH_HOME"] = self.config.dsh_home

        process = await asyncio.create_subprocess_exec(
            *self._argv(executable, args),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd or ROOT),
            env=environment,
        )

        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise DshError("无法创建 dsh 进程管道")

        try:
            process.stdin.write(prompt.encode("utf-8"))
            await process.stdin.drain()
            process.stdin.close()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise DshError(f"写入 dsh 任务失败：{exc}") from exc

        stderr_task = asyncio.create_task(self._read_stream(process.stderr))
        content = ""
        last_text = ""
        captured_session = session_id or ""
        final_error = ""

        async def consume() -> None:
            nonlocal content, last_text, captured_session, final_error
            async for raw in process.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = str(event.get("type") or "")
                if kind == "session":
                    captured_session = str(event.get("sessionId") or captured_session)
                elif kind == "final":
                    content = str(event.get("text") or content)
                    captured_session = str(event.get("sessionId") or captured_session)
                    reason = event.get("reason")
                    if isinstance(reason, dict) and reason.get("kind") == "error":
                        error = reason.get("error") or {}
                        final_error = str(error.get("message") or "Harness 执行失败")
                    await self._emit(on_event, DshEvent("final", text=content))
                elif kind == "text":
                    text = str(event.get("text") or "")
                    if text:
                        last_text = text
                        await self._emit(on_event, DshEvent("text", text=text))
                elif kind == "thinking":
                    text = str(event.get("text") or "")
                    if text:
                        await self._emit(on_event, DshEvent("thinking", text=text))
                elif kind == "tool_call":
                    name = self._tool_name(event)
                    detail = json.dumps(
                        event.get("arguments") or event.get("input") or {},
                        ensure_ascii=False,
                    )[:180]
                    await self._emit(on_event, DshEvent("tool_call", name=name, detail=detail))
                elif kind == "tool_result":
                    name = self._tool_name(event)
                    output = event.get("output") or event.get("result") or ""
                    detail = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
                    await self._emit(on_event, DshEvent("tool_result", name=name, detail=detail[:220]))
                elif kind == "status":
                    reason = event.get("reason")
                    if isinstance(reason, dict) and reason.get("kind") == "error":
                        error = reason.get("error") or {}
                        final_error = str(error.get("message") or "Harness 执行失败")
                    detail = str(event.get("phase") or event.get("status") or event.get("message") or "")[:160]
                    if detail:
                        await self._emit(on_event, DshEvent("status", detail=detail))

        try:
            async with asyncio.timeout(self.config.dsh_timeout):
                await consume()
                stderr = await stderr_task
                exit_code = await process.wait()
        except TimeoutError as exc:
            await self._terminate(process)
            stderr_task.cancel()
            raise DshError(f"dsh 执行超时（{int(self.config.dsh_timeout)} 秒）") from exc
        except asyncio.CancelledError:
            await self._terminate(process)
            stderr_task.cancel()
            raise
        except Exception:
            await self._terminate(process)
            stderr_task.cancel()
            raise
        finally:
            if process.stdin and not process.stdin.is_closing():
                process.stdin.close()
            if patch_path is not None:
                patch_path.unlink(missing_ok=True)

        if exit_code != 0:
            tail = stderr.strip().splitlines()[-3:]
            raise DshError(f"dsh 退出码 {exit_code}：{' | '.join(tail)[:500]}")
        if final_error:
            raise DshError(f"Harness 任务失败：{final_error[:500]}")
        return DshResult(content=content or last_text, session_id=captured_session, exit_code=exit_code)

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(process.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            process.kill()
        await process.wait()

    @staticmethod
    async def _emit(listener: DshListener | None, event: DshEvent) -> None:
        if listener is not None:
            await listener(event)

    def _model_patch(self, model: str) -> Path:
        safe_model = re.sub(r"[^A-Za-z0-9._-]", "", model)[:80]
        if not safe_model:
            raise DshError(f"无效的模型名：{model}")
        lines = [
            "- id: agent-default-model",
            "  config:",
            f"    provider: {self.config.dsh_provider}",
            f"    model: {safe_model}",
        ]
        if self.config.reasoning_effort:
            lines.append(f"    reasoningEffort: {self.config.reasoning_effort}")
        handle, name = tempfile.mkstemp(prefix="dsh-model-", suffix=".yml")
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
        return Path(name)

    @staticmethod
    def _tool_name(event: dict) -> str:
        name = event.get("name") or event.get("tool") or ""
        if not name and isinstance(event.get("toolCall"), dict):
            name = event["toolCall"].get("name", "")
        return str(name)

    @staticmethod
    async def _read_stream(stream: asyncio.StreamReader) -> str:
        chunks: list[str] = []
        async for raw in stream:
            chunks.append(raw.decode("utf-8", "replace"))
        return "".join(chunks)
