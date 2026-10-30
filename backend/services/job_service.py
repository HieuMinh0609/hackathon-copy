"""Quản lý background job ngắn hạn để frontend đọc tiến độ bằng JSON polling."""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

ProgressCallback = Callable[[int, int, str], None]
JobTask = Callable[[ProgressCallback], Any]


@dataclass
class JobState:
    job_id: str
    status: str = "pending"
    current: int = 0
    total: int = 1
    percent: int = 0
    message: str = "Đang chờ xử lý…"
    result: Any = None
    error: str | None = None
    updated_at: float = field(default_factory=time.time)


class JobService:
    """Chạy job trong thread pool và bảo vệ state bằng lock."""

    def __init__(self, max_workers: int = 2, retention_seconds: int = 3600) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aibuddy-job")
        self._retention_seconds = retention_seconds
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def submit(self, task: JobTask) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._cleanup_locked()
            self._jobs[job_id] = JobState(job_id=job_id)
        self._executor.submit(self._run, job_id, task)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._jobs.get(job_id)
            return asdict(state) if state else None

    def _run(self, job_id: str, task: JobTask) -> None:
        self._update(job_id, status="running", message="Đang bắt đầu xử lý…")

        def progress(current: int, total: int, message: str) -> None:
            safe_total = max(1, total)
            safe_current = max(0, min(current, safe_total))
            self._update(
                job_id,
                current=safe_current,
                total=safe_total,
                percent=round(safe_current * 100 / safe_total),
                message=message,
            )

        try:
            result = task(progress)
            self._update(
                job_id,
                status="completed",
                percent=100,
                message="Hoàn tất.",
                result=result,
            )
        except Exception as exc:
            self._update(job_id, status="failed", message="Xử lý thất bại.", error=str(exc))

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if state is None:
                return
            for key, value in changes.items():
                setattr(state, key, value)
            state.updated_at = time.time()

    def _cleanup_locked(self) -> None:
        cutoff = time.time() - self._retention_seconds
        expired = [
            job_id for job_id, state in self._jobs.items()
            if state.status in {"completed", "failed"} and state.updated_at < cutoff
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
