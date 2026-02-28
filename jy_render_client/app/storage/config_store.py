from __future__ import annotations

import json
from pathlib import Path

from app.services.api_client import ApiConfig


class ConfigStore:
    def __init__(self, store_path: Path):
        self.store_path = store_path
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> ApiConfig:
        defaults = ApiConfig()
        raw = self._load_raw()
        try:
            return ApiConfig(
                base_url=str(raw.get("base_url", defaults.base_url)),
                api_key=str(raw.get("api_key", defaults.api_key)),
                jobs_endpoint=str(raw.get("jobs_endpoint", defaults.jobs_endpoint)),
                health_endpoint=str(raw.get("health_endpoint", defaults.health_endpoint)),
                connect_timeout=float(raw.get("connect_timeout", defaults.connect_timeout)),
                read_timeout=float(raw.get("read_timeout", defaults.read_timeout)),
            ).normalize()
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            return defaults

    def load_poll_interval_seconds(self) -> int:
        raw = self._load_raw()
        try:
            value = int(raw.get("poll_interval_seconds", 3))
        except (TypeError, ValueError):
            value = 3
        return max(1, min(60, value))

    def save(self, config: ApiConfig) -> None:
        normalized = config.normalize()
        existing = self._load_raw()
        data = {
            "base_url": normalized.base_url,
            "api_key": normalized.api_key,
            "jobs_endpoint": normalized.jobs_endpoint,
            "health_endpoint": normalized.health_endpoint,
            "connect_timeout": normalized.connect_timeout,
            "read_timeout": normalized.read_timeout,
            "poll_interval_seconds": int(existing.get("poll_interval_seconds", 3)),
        }
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_raw(self) -> dict:
        defaults = {
            "base_url": ApiConfig.base_url,
            "api_key": ApiConfig.api_key,
            "jobs_endpoint": ApiConfig.jobs_endpoint,
            "health_endpoint": ApiConfig.health_endpoint,
            "connect_timeout": ApiConfig.connect_timeout,
            "read_timeout": ApiConfig.read_timeout,
            "poll_interval_seconds": 3,
        }
        if not self.store_path.exists():
            self.store_path.write_text(
                json.dumps(defaults, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return defaults
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return defaults
            return raw
        except (json.JSONDecodeError, OSError):
            return defaults
