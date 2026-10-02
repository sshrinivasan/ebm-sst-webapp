"""Non-blocking background job runner — in-process thread pool + status store.

Endpoints return HTTP 202 with a ``job_id`` immediately; the frontend polls
``GET /api/report/status/{id}``. Long LLM calls run in background threads
with generous HTTP timeouts. Right-sized for a single-user internal tool;
the upgrade path is Redis + RQ/ARQ behind the same interface.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from .session import SessionError


@dataclass
class Job:
    """One background job with staged progress."""

    id: str
    status: str = "pending"  # pending | running | done | error
    stages: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_stage(self, message: str) -> None:
        self.stages.append({"message": message, "status": "running"})

    def complete_stage(self, message: str) -> None:
        for stage in self.stages:
            if stage["message"] == message:
                stage["status"] = "done"

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "stages": self.stages,
            "error": self.error,
            "created_at": self.created_at,
        }


class JobRunner:
    """Thread-pool job runner with an in-memory status store."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        stage_messages: list[str] | None = None,
        **kwargs: Any,
    ) -> Job:
        """Run ``fn`` in a background thread; returns the Job immediately."""
        job = Job(id=uuid.uuid4().hex)
        for message in stage_messages or []:
            job.add_stage(message)
        with self._lock:
            self._jobs[job.id] = job

        def _run() -> None:
            job.status = "running"
            try:
                job.result = fn(*args, **kwargs)
                job.status = "done"
                for stage in job.stages:
                    stage["status"] = "done"
            except Exception as exc:  # surface any failure to the poller
                job.status = "error"
                job.error = str(exc)
                for stage in job.stages:
                    stage["status"] = "error"

        self._executor.submit(_run)
        return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise SessionError(f"Unknown job id: {job_id}")
        return job

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


# Module-level singleton.
runner = JobRunner()