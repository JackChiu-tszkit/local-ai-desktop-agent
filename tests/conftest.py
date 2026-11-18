import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.config.settings import AppSettings
from app.runtime import build_agent
from app.security.approval_manager import ScriptedApproval
from app.security.permissions import PathGuard, default_protected_prefixes
from app.storage.database import Database
from app.tools.base import ToolContext
from tests.fake_platform import FakePlatform


@pytest.fixture
def workspace(tmp_path):
    folders = {}
    for name in ("downloads", "documents", "desktop", "pictures"):
        path = tmp_path / name
        path.mkdir()
        folders[name] = path
    return folders


@pytest.fixture
def agent_bundle(tmp_path, workspace):
    def factory(decision=True, deny_tools=None, provider=None, settings=None, registry=None):
        chosen = settings or AppSettings(
            data_dir=str(tmp_path / "data"),
            step_timeout_seconds=10,
            task_timeout_seconds=30,
            max_steps=12,
        )
        database = Database(tmp_path / "data" / "agent.db")
        platform = FakePlatform()
        approval = ScriptedApproval(decision=decision, deny_tools=set(deny_tools or []))
        agent = build_agent(
            settings=chosen,
            folders=workspace,
            platform=platform,
            approval=approval,
            database=database,
            provider=provider,
            registry=registry,
        )
        return agent, platform, workspace, approval, database

    return factory


def make_context(folders, platform, tmp_path, approved=False, step_timeout=5):
    now = time.monotonic()
    return ToolContext(
        guard=PathGuard(list(folders.values()), default_protected_prefixes()),
        folders=folders,
        platform=platform,
        cancel_event=type("Event", (), {"is_set": lambda self: False})(),
        task_deadline=now + 30,
        step_deadline=now + step_timeout,
        settings=AppSettings(data_dir=str(tmp_path / "data")),
        approved=approved,
        screenshot_dir=tmp_path / "shots",
    )
