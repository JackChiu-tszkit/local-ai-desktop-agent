"""Launch, focus, and close ordinary applications. No arbitrary executables."""

from __future__ import annotations

import time

from pydantic import BaseModel

from app.storage.models import ToolResult
from app.tools.base import ToolContext

KNOWN_APPS = {
    "notepad": "notepad.exe",
    "Notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "Calculator": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "Paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "File Explorer": "explorer.exe",
}


class LaunchArgs(BaseModel):
    application: str
    path: str | None = None


class WindowTitleArgs(BaseModel):
    title: str


class EmptyArgs(BaseModel):
    pass


def launch_app(args: LaunchArgs, ctx: ToolContext) -> ToolResult:
    key = args.application.strip().lower()
    executable = KNOWN_APPS.get(key)
    if executable is None:
        return ToolResult(ok=False, error="Only an allow-listed ordinary application can be opened", error_code="permission")
    launch_args: list[str] = []
    hint = PathStem(executable)
    if args.path:
        target = ctx.guard.resolve(args.path, ctx.folders)
        if not target.exists():
            return ToolResult(ok=False, error="The path to open does not exist", error_code="not_found")
        launch_args.append(str(target))
        hint = target.name
    ctx.platform.launch(executable, launch_args)
    confirmed = _confirm_launch(ctx, executable, hint)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="The process or window was confirmed" if confirmed else "The launch was requested, but the window was not confirmed",
        message=f"Requested launch of {executable}" + ("" if confirmed else " (window not confirmed)"),
        data={"executable": executable, "issued": True, "confirmed": confirmed},
    )


def _confirm_launch(ctx: ToolContext, executable: str, hint: str) -> bool:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        ctx.check_time()
        titles = ctx.platform.window_titles()
        if hint and any(hint.lower() in title.lower() for title in titles):
            return True
        if executable.lower() != "explorer.exe" and ctx.platform.process_exists(executable):
            return True
        time.sleep(0.15)
    return False


def PathStem(executable: str) -> str:
    return executable.rsplit(".", 1)[0].lower()


def list_windows(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    titles = ctx.platform.window_titles()
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="Read the visible window titles",
        message=f"{len(titles)} visible windows",
        data={"titles": titles, "count": len(titles)},
    )


def get_active_window(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    title = ctx.platform.foreground_title()
    return ToolResult(
        ok=True,
        verified=bool(title),
        verification_detail="Read the foreground window",
        message=title or "The foreground window has no title",
        data={"title": title},
        error=None if title else "There is no foreground window",
        error_code=None if title else "not_found",
    )


def focus_window(args: WindowTitleArgs, ctx: ToolContext) -> ToolResult:
    focused = bool(ctx.platform.focus_window(args.title))
    return ToolResult(
        ok=focused,
        verified=focused,
        verification_detail="The foreground window title matches" if focused else "Could not bring the target window to the foreground",
        message=f"Focused {args.title}" if focused else f"Window not found: {args.title}",
        error=None if focused else "The window is not ready",
        error_code=None if focused else "window_not_ready",
    )


def close_application(args: WindowTitleArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Closing an application requires confirmation for this action")
    closed = bool(ctx.platform.close_window(args.title))
    still_open = any(args.title.lower() in title.lower() for title in ctx.platform.window_titles())
    verified = closed and not still_open
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="The window title is gone" if verified else "After the close request the window is still present or was not found",
        message=f"Requested close of {args.title}",
        error=None if verified else "Could not confirm that the window closed",
        error_code=None if verified else "verification_failed",
    )
