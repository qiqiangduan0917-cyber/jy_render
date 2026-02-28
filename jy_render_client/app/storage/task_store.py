from __future__ import annotations

import json
from pathlib import Path

from app.models.task import Task


class TaskStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[Task]:
        if not self.store_path.exists():
            return []
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            return [Task.from_dict(x) for x in raw if isinstance(x, dict)]
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, tasks: list[Task]) -> None:
        data = [task.to_dict() for task in tasks]
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
