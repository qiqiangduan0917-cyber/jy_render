from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from app.services.api_client import ApiClient, ApiConfig


class DownloadWorker(QThread):
    progress_changed = Signal(int, str)
    log = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, config: ApiConfig, job_id: str, save_path: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.job_id = job_id
        self.save_path = Path(save_path)

    def run(self) -> None:
        client = ApiClient(self.config)
        try:
            self.log.emit(f"Downloading job {self.job_id}")

            def on_progress(written: int, total: int, elapsed: float) -> None:
                pct = int((written / total) * 100) if total else 0
                speed = written / elapsed / 1024 / 1024
                total_mb = total / 1024 / 1024 if total else 0.0
                txt = (
                    f"{written / 1024 / 1024:.2f} MB / {total_mb:.2f} MB, {speed:.2f} MB/s"
                )
                self.progress_changed.emit(pct, txt)

            client.download_job(self.job_id, self.save_path, on_progress)
            self.finished_ok.emit(str(self.save_path))
        except Exception as exc:
            self.failed.emit(str(exc))
