"""Wire the desktop agent without importing UI modules."""

from __future__ import annotations

import threading
from pathlib import Path

from app.agent.executor import StepExecutor
from app.agent.orchestrator import DesktopAgent
from app.agent.planner import Planner
from app.config.settings import AppSettings
from app.llm.cloud_provider import CloudProvider
from app.llm.ollama_provider import OllamaProvider
from app.platform.winlib import discover_known_folders
from app.security.approval_manager import ApprovalManager
from app.security.audit import AuditLog
from app.security.permissions import PathGuard, default_protected_prefixes, is_drive_root
from app.storage.database import Database
from app.storage.secrets import load_api_key
from app.tools.registry import ToolRegistry, build_registry


def runtime_folders(settings: AppSettings, override: dict[str, Path] | None = None) -> dict[str, Path]:
    if override is not None:
        return override
    folders = discover_known_folders()
    protected = default_protected_prefixes()
    guard = PathGuard(list(folders.values()) or [Path.home()], protected)
    del guard
    for index, raw in enumerate(settings.extra_roots):
        path = Path(raw)
        if not path.exists() or not path.is_dir() or is_drive_root(path):
            continue
        try:
            PathGuard(list(folders.values()) + [path], protected).resolve(str(path))
        except PermissionError:
            continue
        folders[f"extra_{index}"] = path.resolve()
    return folders


def build_provider(settings: AppSettings):
    if settings.provider == "cloud":
        if not settings.cloud_enabled:
            return None
        return CloudProvider(settings, load_api_key())
    return OllamaProvider(settings)


def build_agent(
    *,
    settings: AppSettings,
    folders: dict[str, Path] | None = None,
    platform=None,
    approval=None,
    database: Database | None = None,
    provider=None,
    cancel_event=None,
    registry: ToolRegistry | None = None,
) -> DesktopAgent:
    selected_folders = runtime_folders(settings, folders)
    if platform is None:
        from app.platform.ops import WindowsPlatform

        platform = WindowsPlatform()
    if database is None:
        database = Database(settings.resolved_data_dir() / "agent.db")
    if registry is None:
        registry = build_registry()
    if provider is None and folders is None:
        provider = build_provider(settings)
    if approval is None:
        approval = ApprovalManager(lambda _preview: False)
    if cancel_event is None:
        cancel_event = threading.Event()
    audit = AuditLog(database)
    planner = Planner(registry, settings, provider)
    executor = StepExecutor(registry, approval, audit, database)
    return DesktopAgent(
        settings=settings,
        registry=registry,
        planner=planner,
        executor=executor,
        database=database,
        folders=selected_folders,
        platform=platform,
        cancel_event=cancel_event,
        provider=provider,
    )
