from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .worker import Worker


class WorkerRegistry:
    """Thread ↔ Worker 的订阅关系，用于事件直通（Fast Path）。"""

    def __init__(self) -> None:
        self._workers: dict[str, "Worker"] = {}

    def subscribe(self, thread_id: str, worker: "Worker") -> None:
        self._workers[thread_id] = worker

    def unsubscribe(self, thread_id: str, worker: "Worker") -> None:
        if self._workers.get(thread_id) is worker:
            self._workers.pop(thread_id, None)

    def get(self, thread_id: str) -> "Worker | None":
        worker = self._workers.get(thread_id)
        if worker is not None and worker.finished:
            self._workers.pop(thread_id, None)
            return None
        return worker
