from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models.task import Task, now_iso
from app.services.api_client import ApiConfig
from app.services.download_worker import DownloadWorker
from app.services.task_poller import TERMINAL_STATES, TaskPoller
from app.services.upload_worker import UploadRenderWorker
from app.storage.config_store import ConfigStore
from app.storage.task_store import TaskStore
from app.utils.logger import attach_ui_logger


class MainWindow(QMainWindow):
    ui_log_signal = Signal(str)

    def __init__(
        self,
        root_dir: Path,
        logger: logging.Logger,
        config_path: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.root_dir = root_dir
        self.logger = logger
        self.setWindowTitle("剪映云渲染助手")
        self.resize(1320, 900)

        self.config_store = ConfigStore(config_path or (self.root_dir / "config.json"))
        self.api_config = self.config_store.load()
        self.poll_interval_seconds = self.config_store.load_poll_interval_seconds()
        self.store = TaskStore(self.root_dir / "tasks.json")
        self.tasks: list[Task] = self.store.load()
        self.selected_draft_path: str = ""
        self.selected_save_dir: str = ""
        self.upload_worker: UploadRenderWorker | None = None
        self.download_worker: DownloadWorker | None = None
        self.active_upload_task_id: str | None = None
        self.active_download_task_id: str | None = None
        self.pending_auto_download_task_ids: list[str] = []
        self.pending_upload_items: list[dict[str, str]] = []
        self.batch_upload_total: int = 0
        self.batch_upload_done: int = 0
        self.batch_upload_failed: int = 0

        self._build_ui()
        self._apply_styles()
        attach_ui_logger(self.logger, self.ui_log_signal.emit)
        self.ui_log_signal.connect(self._append_log)
        self._init_poller()
        self._render_table()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(20, 18, 20, 18)
        main_layout.setSpacing(14)

        task_box = QGroupBox("任务设置")
        task_grid = QGridLayout(task_box)
        task_grid.setHorizontalSpacing(10)
        task_grid.setVerticalSpacing(10)

        self.draft_path_edit = QLineEdit()
        self.draft_path_edit.setReadOnly(True)
        self.save_dir_edit = QLineEdit()
        self.save_dir_edit.setReadOnly(True)

        self.btn_choose_draft_root = QPushButton("选择草稿根目录")
        self.btn_choose_save_dir = QPushButton("选择输出目录")
        self.btn_start = QPushButton("开始上传并渲染")
        self.btn_clear_tasks = QPushButton("清空任务列表")
        self.btn_clear_logs = QPushButton("清空日志")

        self.btn_choose_draft_root.clicked.connect(self.on_choose_draft_root)
        self.btn_choose_save_dir.clicked.connect(self.on_choose_save_dir)
        self.btn_start.clicked.connect(self.on_start_upload_render)
        self.btn_clear_tasks.clicked.connect(self.on_clear_tasks_clicked)
        self.btn_clear_logs.clicked.connect(self.on_clear_logs_clicked)

        self.upload_progress = QProgressBar()
        self.upload_progress.setRange(0, 100)
        self.upload_status_label = QLabel("-")
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_status_label = QLabel("-")

        task_grid.addWidget(self.btn_choose_draft_root, 0, 0)
        task_grid.addWidget(self.draft_path_edit, 0, 1, 1, 3)
        task_grid.addWidget(self.btn_choose_save_dir, 1, 0)
        task_grid.addWidget(self.save_dir_edit, 1, 1, 1, 3)
        task_grid.addWidget(self.btn_start, 3, 0, 1, 4)
        task_grid.addWidget(QLabel("上传进度"), 4, 0)
        task_grid.addWidget(self.upload_progress, 4, 1, 1, 2)
        task_grid.addWidget(self.upload_status_label, 4, 3)
        task_grid.addWidget(QLabel("下载进度"), 5, 0)
        task_grid.addWidget(self.download_progress, 5, 1, 1, 2)
        task_grid.addWidget(self.download_status_label, 5, 3)
        task_grid.addWidget(self.btn_clear_tasks, 6, 0, 1, 2)
        task_grid.addWidget(self.btn_clear_logs, 6, 2, 1, 2)
        main_layout.addWidget(task_box)

        bottom_box = QGroupBox("任务列表与日志")
        bottom_layout = QVBoxLayout(bottom_box)
        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["任务ID", "标题", "状态", "创建时间", "操作"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.table)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        splitter.addWidget(self.log_text)
        splitter.setSizes([470, 260])
        bottom_layout.addWidget(splitter)
        main_layout.addWidget(bottom_box)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f5f7fb;
                color: #182034;
                font-size: 13px;
            }
            QMainWindow {
                background: #f5f7fb;
            }
            #headerCard {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #0f2f54, stop: 1 #1f6aa5
                );
                border-radius: 14px;
            }
            #headerTitle {
                color: #ffffff;
                font-size: 28px;
                font-weight: 700;
            }
            #headerSubTitle {
                color: #d8e9f8;
                font-size: 13px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d6deea;
                border-radius: 10px;
                margin-top: 10px;
                font-weight: 600;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                color: #233046;
            }
            QLineEdit, QPlainTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #ccd6e4;
                border-radius: 8px;
                padding: 6px;
            }
            QPushButton {
                background: #1f6aa5;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2c7fc1;
            }
            QPushButton:disabled {
                background: #94a8bc;
                color: #edf2f7;
            }
            QProgressBar {
                border: 1px solid #c9d4e2;
                border-radius: 7px;
                text-align: center;
                background: #eef3f8;
                min-height: 18px;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #3ca45a;
            }
            QHeaderView::section {
                background: #edf2f8;
                border: none;
                border-right: 1px solid #d8e0eb;
                border-bottom: 1px solid #d8e0eb;
                padding: 6px;
                font-weight: 600;
            }
            """
        )

    def _init_poller(self) -> None:
        self.poller = TaskPoller(
            config_provider=self._current_config,
            tasks_provider=lambda: self.tasks,
            interval_seconds=self.poll_interval_seconds,
            parent=self,
        )
        self.poller.task_updated.connect(self.on_task_polled)
        self.poller.log.connect(self.logger.info)
        self.poller.start()

    def _current_config(self) -> ApiConfig:
        self.api_config = self.config_store.load()
        latest_interval = self.config_store.load_poll_interval_seconds()
        if latest_interval != self.poll_interval_seconds:
            self.poll_interval_seconds = latest_interval
            self.poller.set_interval(self.poll_interval_seconds)
        return ApiConfig(**vars(self.api_config))

    def on_choose_draft_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择草稿根目录", str(self.root_dir))
        if not folder:
            return
        self.selected_draft_path = folder
        self.draft_path_edit.setText(folder)

    def on_choose_save_dir(self) -> None:
        default_dir = self.selected_save_dir or str(self.root_dir)
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录", default_dir)
        if not folder:
            return
        self.selected_save_dir = folder
        self.save_dir_edit.setText(folder)

    def on_start_upload_render(self) -> None:
        cfg = self._current_config()
        draft_root = self.selected_draft_path

        if not cfg.base_url:
            self._show_error("请先配置有效的服务端 Base URL。")
            return
        if not draft_root or not Path(draft_root).exists() or not Path(draft_root).is_dir():
            self._show_error("请先选择有效的草稿根目录。")
            return
        if self.upload_worker and self.upload_worker.isRunning():
            self._show_error("当前已有上传任务在进行中。")
            return

        root_path = Path(draft_root)
        draft_dirs = self._collect_draft_dirs(root_path)
        if not draft_dirs:
            self._show_error("未在所选根目录下找到可上传的草稿。")
            return

        now_tag = datetime.now().strftime("%Y%m%d%H%M%S")
        self.pending_upload_items = []
        self.batch_upload_total = len(draft_dirs)
        self.batch_upload_done = 0
        self.batch_upload_failed = 0

        for idx, draft_dir in enumerate(draft_dirs, start=1):
            local_task_id = f"local-{now_tag}-{idx:04d}"
            task = Task(
                task_id=local_task_id,
                draft_id=None,
                title=draft_dir.name,
                status="UPLOADING",
                progress="0%",
                created_at=now_iso(),
                updated_at=now_iso(),
                draft_path=str(draft_dir),
                assets_mode=None,
                assets=[],
            )
            self._upsert_task(task)
            self.pending_upload_items.append(
                {
                    "local_task_id": local_task_id,
                    "draft_path": str(draft_dir),
                    "title": draft_dir.name,
                }
            )

        self.active_upload_task_id = None
        self.upload_progress.setValue(0)
        self.upload_status_label.setText(f"0/{self.batch_upload_total}")
        self.btn_start.setEnabled(False)
        self.logger.info(
            "开始批量创建任务，draft_root=%s total=%s",
            draft_root,
            self.batch_upload_total,
        )
        self._start_next_upload()
    def _collect_draft_dirs(self, draft_root: Path) -> list[Path]:
        child_dirs = sorted([p for p in draft_root.iterdir() if p.is_dir()], key=lambda p: p.name.lower())
        valid_children = [p for p in child_dirs if self._dir_has_files(p)]
        if valid_children:
            return valid_children
        if self._dir_has_files(draft_root):
            return [draft_root]
        return []

    @staticmethod
    def _dir_has_files(folder: Path) -> bool:
        return any(p.is_file() for p in folder.rglob("*"))

    def _start_next_upload(self) -> None:
        if not self.pending_upload_items:
            self.btn_start.setEnabled(True)
            summary = (
                f"批量上传完成：成功 {self.batch_upload_done}，失败 {self.batch_upload_failed}，"
                f"总计 {self.batch_upload_total}。"
            )
            self.upload_status_label.setText(summary)
            self.logger.info(summary)
            return

        item = self.pending_upload_items.pop(0)
        self.active_upload_task_id = item["local_task_id"]
        self.upload_progress.setValue(0)
        self.upload_status_label.setText(
            f"{self.batch_upload_done + self.batch_upload_failed + 1}/{self.batch_upload_total} "
            f"{item['title']}"
        )
        cfg = self._current_config()
        self.upload_worker = UploadRenderWorker(cfg, item["draft_path"], item["title"], self)
        self.upload_worker.progress_changed.connect(self._on_upload_progress)
        self.upload_worker.log.connect(self.logger.info)
        self.upload_worker.finished_ok.connect(self._on_upload_render_finished)
        self.upload_worker.failed.connect(self._on_upload_render_failed)
        self.upload_worker.start()

    def _on_upload_progress(self, pct: int, text: str) -> None:
        pct = max(0, min(100, pct))
        self.upload_progress.setValue(pct)
        prefix = f"{self.batch_upload_done + self.batch_upload_failed + 1}/{self.batch_upload_total}"
        self.upload_status_label.setText(f"{prefix} {text}")
        if self.active_upload_task_id:
            task = self._find_task(self.active_upload_task_id)
            if task:
                task.progress = f"{pct}%"
                task.updated_at = now_iso()

    def _on_upload_render_finished(self, result: dict) -> None:
        if not self.active_upload_task_id:
            return
        old = self._find_task(self.active_upload_task_id)
        if not old:
            return
        job_id = str(result.get("job_id", ""))
        if not job_id:
            self._on_upload_render_failed("create_job response missing job_id")
            return

        old.task_id = job_id
        old.draft_id = None
        old.status = str(result.get("status") or "queued").upper()
        old.progress = old.progress if old.progress != "-" else "0%"
        old.updated_at = now_iso()
        old.error = None

        self.batch_upload_done += 1
        self.active_upload_task_id = job_id
        self.upload_progress.setValue(100)
        self.logger.info("Create job success: job_id=%s status=%s", old.task_id, old.status)
        self._save_tasks()
        self._render_table()
        self.poller.poll_now()
        QTimer.singleShot(0, self._start_next_upload)

    def _on_upload_render_failed(self, err: str) -> None:
        self.logger.error("Create job failed: %s", err)
        self.batch_upload_failed += 1
        if self.active_upload_task_id:
            task = self._find_task(self.active_upload_task_id)
            if task:
                task.status = "FAILED"
                task.error = err
                task.updated_at = now_iso()
                self._save_tasks()
                self._render_table()
        QTimer.singleShot(0, self._start_next_upload)

    def on_task_polled(self, data: dict) -> None:
        task_id = str(data.get("task_id", ""))
        task = self._find_task(task_id)
        if not task:
            return
        old_status = task.status
        task.status = str(data.get("status", task.status)).upper()
        task.progress = str(data.get("progress", task.progress))
        output_url = data.get("output_url")
        if output_url:
            task.output_url = str(output_url)
        task.updated_at = now_iso()
        self._save_tasks()
        self._render_table()
        if task.status != old_status:
            self.logger.info("Task %s status: %s -> %s", task.task_id, old_status, task.status)
            if task.status == "DONE" and not task.output_path:
                self._enqueue_auto_download(task.task_id)

    def on_download_clicked(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        if task.status != "DONE":
            self._show_error("任务尚未完成，暂不能下载。")
            return
        self._start_download(task, auto=False)

    def _on_download_progress(self, pct: int, text: str) -> None:
        self.download_progress.setValue(max(0, min(100, pct)))
        self.download_status_label.setText(text)

    def _on_download_finished(self, save_path: str) -> None:
        self.download_progress.setValue(100)
        task = self._find_task(self.active_download_task_id or "")
        if task:
            task.output_path = save_path
            task.updated_at = now_iso()
            self._save_tasks()
            self._render_table()
        self.logger.info("下载完成: %s", save_path)
        QTimer.singleShot(0, self._start_next_auto_download)

    def _on_download_failed(self, err: str) -> None:
        self.logger.error("下载失败: %s", err)
        QMessageBox.warning(self, "下载失败", err)
        QTimer.singleShot(0, self._start_next_auto_download)

    def _enqueue_auto_download(self, task_id: str) -> None:
        if task_id in self.pending_auto_download_task_ids:
            return
        self.pending_auto_download_task_ids.append(task_id)
        QTimer.singleShot(0, self._start_next_auto_download)

    def _start_next_auto_download(self) -> None:
        if self.download_worker and self.download_worker.isRunning():
            return
        while self.pending_auto_download_task_ids:
            task_id = self.pending_auto_download_task_ids.pop(0)
            task = self._find_task(task_id)
            if not task or task.status != "DONE" or task.output_path:
                continue
            self._start_download(task, auto=True)
            return

    def _start_download(self, task: Task, auto: bool) -> None:
        if self.download_worker and self.download_worker.isRunning():
            if not auto:
                self._show_error("当前已有下载任务在进行中。")
            return

        if auto:
            selected_dir = self.selected_save_dir or str(self.root_dir)
        else:
            default_dir = self.selected_save_dir or str(self.root_dir)
            selected_dir = QFileDialog.getExistingDirectory(self, "选择输出目录", default_dir)
            if not selected_dir:
                return

        self.selected_save_dir = selected_dir
        self.save_dir_edit.setText(selected_dir)

        filename = f"{task.title or task.task_id}.mp4"
        save_path = str(Path(selected_dir) / filename)
        self.active_download_task_id = task.task_id
        self.download_progress.setValue(0)
        self.download_status_label.setText("-")
        self.download_worker = DownloadWorker(self._current_config(), task.task_id, save_path, self)
        self.download_worker.progress_changed.connect(self._on_download_progress)
        self.download_worker.log.connect(self.logger.info)
        self.download_worker.finished_ok.connect(self._on_download_finished)
        self.download_worker.failed.connect(self._on_download_failed)
        self.download_worker.start()

    def on_open_folder_clicked(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if task and task.output_path:
            path = Path(task.output_path).parent
        else:
            path = Path(self.selected_save_dir) if self.selected_save_dir else self.root_dir
        if not path.exists():
            self._show_error("输出目录不存在。")
            return
        os.startfile(str(path))

    def on_show_detail_clicked(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        data = task.to_dict()
        text = "\n".join([f"{k}: {v}" for k, v in data.items()])
        QMessageBox.information(self, "任务详情", text)

    def on_retry_clicked(self, task_id: str) -> None:
        task = self._find_task(task_id)
        if not task:
            return
        if self.upload_worker and self.upload_worker.isRunning():
            self._show_error("当前已有上传任务在进行中。")
            return
        cfg = self._current_config()
        if not cfg.base_url:
            self._show_error("请先配置有效的服务端 Base URL。")
            return
        if not task.draft_path or not Path(task.draft_path).exists():
            self._show_error("重试所需的草稿目录不存在。")
            return

        # Retry only this task's draft path; do not replace selected draft root.
        task.status = "UPLOADING"
        task.progress = "0%"
        task.error = None
        task.updated_at = now_iso()
        self._save_tasks()
        self._render_table()

        self.pending_upload_items = []
        self.batch_upload_total = 1
        self.batch_upload_done = 0
        self.batch_upload_failed = 0
        self.active_upload_task_id = task.task_id
        self.upload_progress.setValue(0)
        self.upload_status_label.setText(f"1/1 {task.title}")
        self.btn_start.setEnabled(False)

        self.upload_worker = UploadRenderWorker(cfg, task.draft_path, task.title, self)
        self.upload_worker.progress_changed.connect(self._on_upload_progress)
        self.upload_worker.log.connect(self.logger.info)
        self.upload_worker.finished_ok.connect(self._on_upload_render_finished)
        self.upload_worker.failed.connect(self._on_upload_render_failed)
        self.upload_worker.start()

    def _find_task(self, task_id: str) -> Task | None:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None

    def _upsert_task(self, new_task: Task) -> None:
        for idx, task in enumerate(self.tasks):
            if task.task_id == new_task.task_id:
                self.tasks[idx] = new_task
                self._save_tasks()
                self._render_table()
                return
        self.tasks.insert(0, new_task)
        self._save_tasks()
        self._render_table()

    def _save_tasks(self) -> None:
        self.store.save(self.tasks)

    def _render_table(self) -> None:
        self.table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            self.table.setItem(row, 0, QTableWidgetItem(task.task_id))
            self.table.setItem(row, 1, QTableWidgetItem(task.title))
            self.table.setItem(row, 2, QTableWidgetItem(task.status))
            self.table.setItem(row, 3, QTableWidgetItem(task.created_at))

            actions = QWidget()
            layout = QHBoxLayout(actions)
            layout.setContentsMargins(2, 2, 2, 2)
            btn_detail = QPushButton("详情")
            btn_download = QPushButton("下载")
            btn_open = QPushButton("打开目录")
            btn_retry = QPushButton("重试")
            btn_detail.clicked.connect(lambda *_, tid=task.task_id: self.on_show_detail_clicked(tid))
            btn_download.clicked.connect(lambda *_, tid=task.task_id: self.on_download_clicked(tid))
            btn_open.clicked.connect(lambda *_, tid=task.task_id: self.on_open_folder_clicked(tid))
            btn_retry.clicked.connect(lambda *_, tid=task.task_id: self.on_retry_clicked(tid))

            if task.status != "DONE":
                btn_download.setEnabled(False)
            if task.status not in {"FAILED", "CANCELLED", "CANCELED"}:
                btn_retry.setEnabled(False)
            if task.status in TERMINAL_STATES and not task.output_path:
                btn_open.setEnabled(False)

            layout.addWidget(btn_detail)
            layout.addWidget(btn_download)
            layout.addWidget(btn_open)
            layout.addWidget(btn_retry)
            self.table.setCellWidget(row, 4, actions)

        self.table.resizeColumnsToContents()

    def _append_log(self, msg: str) -> None:
        self.log_text.appendPlainText(msg)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())

    def on_clear_tasks_clicked(self) -> None:
        if self.upload_worker and self.upload_worker.isRunning():
            self._show_error("上传进行中，无法清空任务列表。")
            return
        if self.download_worker and self.download_worker.isRunning():
            self._show_error("下载进行中，无法清空任务列表。")
            return
        if not self.tasks:
            return
        result = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空任务列表吗？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result != QMessageBox.Yes:
            return
        self.tasks.clear()
        self.pending_upload_items = []
        self.batch_upload_total = 0
        self.batch_upload_done = 0
        self.batch_upload_failed = 0
        self.active_upload_task_id = None
        self.active_download_task_id = None
        self.upload_progress.setValue(0)
        self.upload_status_label.setText("-")
        self.download_progress.setValue(0)
        self.download_status_label.setText("-")
        self._save_tasks()
        self._render_table()
        self.logger.info("任务列表已清空。")

    def on_clear_logs_clicked(self) -> None:
        self.log_text.clear()
        self.logger.info("日志面板已清空。")

    def _show_error(self, msg: str) -> None:
        self.logger.error(msg)
        QMessageBox.warning(self, "错误", msg)

    def closeEvent(self, event) -> None:
        self.logger.info("Closing app...")
        self.poller.stop()
        for worker in [self.upload_worker, self.download_worker]:
            if worker and worker.isRunning():
                worker.quit()
                worker.wait(2000)
        self._save_tasks()
        super().closeEvent(event)

