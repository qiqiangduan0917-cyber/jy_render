from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Task:
    task_id: str
    title: str
    status: str
    draft_id: str | None = None
    progress: str = "-"
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    output_url: str | None = None
    output_path: str | None = None
    error: str | None = None
    canceled_local: bool = False
    draft_path: str | None = None
    assets_mode: str | None = None
    assets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "status": self.status,
            "draft_id": self.draft_id,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "output_url": self.output_url,
            "output_path": self.output_path,
            "error": self.error,
            "canceled_local": self.canceled_local,
            "draft_path": self.draft_path,
            "assets_mode": self.assets_mode,
            "assets": self.assets,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            task_id=str(data.get("task_id", "")),
            title=str(data.get("title", "")),
            status=str(data.get("status", "UNKNOWN")),
            draft_id=data.get("draft_id"),
            progress=str(data.get("progress", "-")),
            created_at=str(data.get("created_at", now_iso())),
            updated_at=str(data.get("updated_at", now_iso())),
            output_url=data.get("output_url"),
            output_path=data.get("output_path"),
            error=data.get("error"),
            canceled_local=bool(data.get("canceled_local", False)),
            draft_path=data.get("draft_path"),
            assets_mode=data.get("assets_mode"),
            assets=list(data.get("assets", [])),
        )
