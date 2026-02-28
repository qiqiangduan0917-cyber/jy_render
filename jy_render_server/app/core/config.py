import os
from pathlib import Path
import yaml


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


class Config:
    def __init__(self):
        self.BASE_DIR = ROOT_DIR
        self.YAML_PATH = CONFIG_DIR / "config.yaml"
        self.TEMPLATES_DIR = ROOT_DIR / "templates"

        self.CAPCUT_PROJECTS_DIR = ""
        self.SEARCH_RESULT_X = 300
        self.SEARCH_RESULT_Y = 581
        self.EXPORT_TIMEOUT = 300
        self.POLL_INTERVAL = 3
        self.EXPORT_OUTPUT_DIR = ""

        self._init_template_paths()

        if self.YAML_PATH.exists():
            self.load()

    def _init_template_paths(self):
        d = str(self.TEMPLATES_DIR)
        self.SEARCH_BTN = os.path.join(d, "01_搜索按钮.png")
        self.EXPORT_BTN = os.path.join(d, "02_导出.png")
        self.LOADING_IMG = os.path.join(d, "02_加载中.png")
        self.DO_EXPORT_BTN = os.path.join(d, "03_执行导出.png")
        self.PUBLISH_BTN = os.path.join(d, "04_发布按钮.png")
        self.CANCEL_BTN = os.path.join(d, "05_取消按钮.png")
        self.HOME_BTN = os.path.join(d, "06_回主界面.png")
        self.RESTORE_BTN = os.path.join(d, "07_恢复按钮.png")

    def load(self):
        with open(self.YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.CAPCUT_PROJECTS_DIR = data.get("capcut_projects_dir", self.CAPCUT_PROJECTS_DIR)
        self.SEARCH_RESULT_X = data.get("search_result_x", self.SEARCH_RESULT_X)
        self.SEARCH_RESULT_Y = data.get("search_result_y", self.SEARCH_RESULT_Y)
        self.EXPORT_OUTPUT_DIR = data.get("export_output_dir", self.EXPORT_OUTPUT_DIR)
        self.EXPORT_TIMEOUT = data.get("export_timeout", self.EXPORT_TIMEOUT)
        self.POLL_INTERVAL = data.get("poll_interval", self.POLL_INTERVAL)

    def save(self):
        data = {
            "capcut_projects_dir": self.CAPCUT_PROJECTS_DIR,
            "search_result_x": self.SEARCH_RESULT_X,
            "search_result_y": self.SEARCH_RESULT_Y,
            "export_output_dir": self.EXPORT_OUTPUT_DIR,
            "export_timeout": self.EXPORT_TIMEOUT,
            "poll_interval": self.POLL_INTERVAL,
        }
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(self.YAML_PATH, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


_CONFIG = None


def get_config():
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = Config()
    return _CONFIG
