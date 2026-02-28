import logging

from app.core.paths import LOGS_DIR


def setup_logging() -> None:
    """
    Initialize application-wide logging configuration.
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # Already configured
        return

    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    # 文件输出
    log_path = LOGS_DIR / "app.log"
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 控制台输出
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

