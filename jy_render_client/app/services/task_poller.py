from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from app.models.task import Task
from app.services.api_client import ApiClient, ApiConfig


TERMINAL_STATES = {"DONE", "FAILED", "CANCELED", "CANCELLED"}


@dataclass
class PollResult:
    task_id: str
    status: str
    progress: str
    output_url: str | None
    raw: dict


class StatusPollWorker(QThread):
    polled = Signal(dict)
    failed = Signal(str)

    def __init__(self, config: ApiConfig, task_ids: list[str], parent=None):
        super().__init__(parent)
        self.config = config
        self.task_ids = task_ids

    def run(self) -> None:
        client = ApiClient(self.config)
        for task_id in self.task_ids:
            try:
                data = client.get_job(task_id)
                status = (
                    data.get("status")
                    or data.get("state")
                    or data.get("data", {}).get("status")
                    or "UNKNOWN"
                )
                progress = data.get("progress")
                if progress is None:
                    progress = data.get("data", {}).get("progress")
                status_upper = str(status).upper()
                output_url = None
                if status_upper == "DONE":
                    output_url = (
                        f"{self.config.jobs_endpoint.rstrip('/')}/{task_id}/download"
                    )
                result = PollResult(
                    task_id=task_id,
                    status=status_upper,
                    progress=str(progress) if progress is not None else "-",
                    output_url=output_url,
                    raw=data,
                )
                self.polled.emit(asdict(result))
            except Exception as exc:
                self.failed.emit(f"task_id={task_id}, error={exc}")


class TaskPoller(QObject):
    task_updated = Signal(dict)
    log = Signal(str)

    def __init__(
        self,
        config_provider: Callable[[], ApiConfig],
        tasks_provider: Callable[[], list[Task]],
        interval_seconds: int = 3,
        parent=None,
    ):
        super().__init__(parent)
        self._config_provider = config_provider
        self._tasks_provider = tasks_provider
        self._worker: StatusPollWorker | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self.set_interval(interval_seconds)

    def set_interval(self, seconds: int) -> None:
        ms = max(1, int(seconds)) * 1000
        self._timer.setInterval(ms)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self.log.emit("Task poller started.")

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self.log.emit("Task poller stopped.")
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)

    def poll_now(self) -> None:
        self._on_timeout()

    def _on_timeout(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        task_ids = []
        for task in self._tasks_provider():
            if task.canceled_local:
                continue
            if task.task_id.startswith("local-"):
                continue
            if task.status.upper() in TERMINAL_STATES:
                continue
            task_ids.append(task.task_id)
        if not task_ids:
            return
        self._worker = StatusPollWorker(self._config_provider(), task_ids, parent=self)
        self._worker.polled.connect(self.task_updated.emit)
        self._worker.failed.connect(lambda msg: self.log.emit(f"Poll error: {msg}"))
        self._worker.start()
