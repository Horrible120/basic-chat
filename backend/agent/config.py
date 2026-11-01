from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    """读取极简 .env（KEY=VALUE）；已存在的环境变量优先。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class AgentConfig:
    name: str = "小深"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    router_model: str = "deepseek-chat"
    worker_model: str = "deepseek-chat"
    temperature: float = 0.3
    router_max_tokens: int = 400
    worker_max_tokens: int = 1600
    request_timeout: float = 180.0
    max_workers: int = 3
    max_steps: int = 8
    batch_size: int = 6
    history_limit: int = 16
    spill_chars: int = 300
    rate_limit: int = 12
    rate_window: float = 60.0
    allow_write: bool = True

    @classmethod
    def from_env(cls) -> "AgentConfig":
        load_env_file()
        return cls(
            name=(os.getenv("AGENT_NAME", "小深").strip() or "小深"),
            api_key=os.getenv("LLM_API_KEY", "").strip(),
            base_url=(os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com"),
            router_model=os.getenv("ROUTER_MODEL", "deepseek-chat").strip() or "deepseek-chat",
            worker_model=os.getenv("WORKER_MODEL", "deepseek-chat").strip() or "deepseek-chat",
            temperature=_float("LLM_TEMPERATURE", 0.3),
            router_max_tokens=_int("ROUTER_MAX_TOKENS", 400),
            worker_max_tokens=_int("WORKER_MAX_TOKENS", 1600),
            request_timeout=_float("LLM_TIMEOUT", 180.0),
            max_workers=max(1, _int("MAX_WORKERS", 3)),
            max_steps=max(1, _int("MAX_STEPS", 8)),
            batch_size=max(1, _int("ROUTER_BATCH", 6)),
            history_limit=max(4, _int("HISTORY_LIMIT", 16)),
            spill_chars=max(80, _int("SPILL_CHARS", 300)),
            rate_limit=max(1, _int("RATE_LIMIT", 12)),
            rate_window=max(1.0, _float("RATE_WINDOW", 60.0)),
            allow_write=_bool("AGENT_ALLOW_WRITE", True),
        )

    @property
    def demo_mode(self) -> bool:
        return not self.api_key
