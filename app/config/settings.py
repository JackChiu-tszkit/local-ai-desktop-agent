"""User-editable settings. Secrets are not written to disk."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def default_data_dir() -> Path:
    override = os.environ.get("AGENT_DATA_DIR")
    if override:
        return Path(override)
    root = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(root) / "LocalAIDesktopAgent"


class AppSettings(BaseModel):
    provider: Literal["ollama", "cloud"] = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_vision: bool = False
    cloud_enabled: bool = False
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_model: str = "gpt-4o-mini"
    cloud_vision: bool = False
    cloud_allow_screenshots: bool = False
    cloud_allow_file_contents: bool = False
    cloud_allow_paths: bool = False
    max_steps: int = 12
    max_retries: int = 2
    max_replans: int = 2
    step_timeout_seconds: float = 45
    task_timeout_seconds: float = 180
    max_search_results: int = 200
    max_hash_bytes: int = 200 * 1024 * 1024
    extra_roots: list[str] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    data_dir: str = ""

    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir)
        return default_data_dir()

    def settings_path(self) -> Path:
        return self.resolved_data_dir() / "settings.json"

    def save(self, path: Path | None = None) -> None:
        target = path or self.settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self.model_dump()
        payload.pop("data_dir", None)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> AppSettings:
        data: dict[str, Any] = {}
        source = path
        if source is None and os.environ.get("AGENT_DATA_DIR"):
            candidate = Path(os.environ["AGENT_DATA_DIR"]) / "settings.json"
            if candidate.exists():
                source = candidate
        elif source is None:
            candidate = default_data_dir() / "settings.json"
            if candidate.exists():
                source = candidate
        if source is not None and Path(source).exists():
            loaded = json.loads(Path(source).read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        env_map = {
            "AGENT_PROVIDER": "provider",
            "OLLAMA_BASE_URL": "ollama_base_url",
            "OLLAMA_MODEL": "ollama_model",
            "CLOUD_BASE_URL": "cloud_base_url",
            "CLOUD_MODEL": "cloud_model",
        }
        for env_name, field_name in env_map.items():
            value = os.environ.get(env_name)
            if value:
                data[field_name] = value
        for env_name, field_name in (
            ("CLOUD_ENABLED", "cloud_enabled"),
            ("CLOUD_ALLOW_SCREENSHOTS", "cloud_allow_screenshots"),
            ("CLOUD_ALLOW_FILE_CONTENTS", "cloud_allow_file_contents"),
            ("CLOUD_ALLOW_PATHS", "cloud_allow_paths"),
            ("OLLAMA_VISION", "ollama_vision"),
        ):
            raw = os.environ.get(env_name)
            if raw is not None and raw != "":
                data[field_name] = raw.strip().lower() in {"1", "true", "yes", "on"}
        if os.environ.get("AGENT_DATA_DIR"):
            data["data_dir"] = os.environ["AGENT_DATA_DIR"]
        return cls.model_validate(data)
