from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable


class UiLogHandler(logging.Handler):
    def __init__(self, emit_fn: Callable[[str], None]):
        super().__init__()
        self._emit_fn = emit_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._emit_fn(msg)
        except Exception:
            self.handleError(record)


def configure_logging(root_dir: Path) -> logging.Logger:
    log_dir = root_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("client")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(threadName)s - %(message)s"
    )
    try:
        file_handler = RotatingFileHandler(
            log_dir / "app.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # If file logging is blocked (permission/lock), keep app alive with stderr logging.
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        logger.warning("File logging unavailable, fallback to stderr.")

    logger.propagate = False
    return logger


def attach_ui_logger(logger: logging.Logger, emit_fn: Callable[[str], None]) -> None:
    handler = UiLogHandler(emit_fn)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
