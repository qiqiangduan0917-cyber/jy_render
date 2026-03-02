import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.utils.logger import configure_logging


def main() -> int:
    app_root_dir = Path(__file__).resolve().parent
    app_data_dir = app_root_dir / "runtime"
    app_data_dir.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(app_data_dir)

    app = QApplication(sys.argv)
    icon_path = app_root_dir / "assets" / "logo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow(
        root_dir=app_data_dir,
        logger=logger,
        config_path=app_root_dir / "config.json",
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
