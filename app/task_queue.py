from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from app.config import Settings
from app.task_runner import run_task


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskJob:
    settings: Settings
    task_id: int


_jobs: queue.Queue[TaskJob] = queue.Queue()
_worker_started = False
_worker_lock = threading.Lock()


def enqueue_task(settings: Settings, task_id: int) -> None:
    _ensure_worker()
    _jobs.put(TaskJob(settings=settings, task_id=task_id))


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        thread = threading.Thread(
            target=_worker_loop,
            name="audit-task-worker",
            daemon=True,
        )
        thread.start()
        _worker_started = True


def _worker_loop() -> None:
    while True:
        job = _jobs.get()
        try:
            run_task(job.settings, job.task_id)
        except Exception:  # noqa: BLE001 - keep the worker alive for later jobs.
            logger.exception("Audit task worker failed for task_id=%s", job.task_id)
        finally:
            _jobs.task_done()
