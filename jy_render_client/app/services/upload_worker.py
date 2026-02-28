from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.services.api_client import ApiClient, ApiConfig, ApiError


class UploadRenderWorker(QThread):
    progress_changed = Signal(int, str)
    log = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        config: ApiConfig,
        draft_path: str,
        title: str,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.draft_path = Path(draft_path)
        self.title = title

    def run(self) -> None:
        client = ApiClient(self.config)
        try:
            self.log.emit("Packing draft directory and creating render job...")

            def on_zip_progress(done: int, total: int, elapsed: float) -> None:
                pct = int((done / total) * 40) if total else 0
                speed = done / elapsed if elapsed > 0 else 0
                txt = (
                    f"Packing files {done}/{total}, "
                    f"{speed:.1f} files/s"
                )
                self.progress_changed.emit(pct, txt)

            def on_upload_progress(read_bytes: int, total: int, elapsed: float) -> None:
                net_pct = int((read_bytes / total) * 60) if total else 0
                pct = min(99, 40 + net_pct)
                speed = read_bytes / elapsed / 1024 / 1024 if elapsed > 0 else 0
                txt = (
                    f"Uploading zip {read_bytes / 1024 / 1024:.2f}MB/"
                    f"{(total / 1024 / 1024 if total else 0):.2f}MB, "
                    f"{speed:.2f} MB/s"
                )
                self.progress_changed.emit(pct, txt)

            resp = client.create_job(self.draft_path, on_zip_progress, on_upload_progress)
            data = resp.get("data") if isinstance(resp, dict) else None
            if not isinstance(data, dict):
                raise ApiError(f"Create job response missing data: {resp}")
            job_id = data.get("job_id")
            status = data.get("status")
            if not job_id:
                raise ApiError(f"Create job response missing job_id: {resp}")
            self.progress_changed.emit(100, "Submitted")
            self.log.emit(f"Create job success. job_id={job_id}, status={status}")
            time.sleep(0.1)
            self.finished_ok.emit(
                {
                    "job_id": str(job_id),
                    "status": str(status or "queued"),
                    "create_response": resp,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))
