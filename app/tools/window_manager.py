"""Launch, focus, and close ordinary applications. No arbitrary executables."""

from __future__ import annotations

import time

from pydantic import BaseModel

from app.storage.models import ToolResult
from app.tools.base import ToolContext

KNOWN_APPS = {
    "notepad": "notepad.exe",
    "记事本": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "计算器": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "画图": "mspaint.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "文件资源管理器": "explorer.exe",
    "资源管理器": "explorer.exe",
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
        return ToolResult(ok=False, error="只能打开预先允许的普通应用", error_code="permission")
    launch_args: list[str] = []
    hint = PathStem(executable)
    if args.path:
        target = ctx.guard.resolve(args.path, ctx.folders)
        if not target.exists():
            return ToolResult(ok=False, error="要打开的路径不存在", error_code="not_found")
        launch_args.append(str(target))
        hint = target.name
    ctx.platform.launch(executable, launch_args)
    confirmed = _confirm_launch(ctx, executable, hint)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="进程或窗口已确认" if confirmed else "已发出启动请求，但未确认窗口",
        message=f"已请求启动 {executable}" + ("" if confirmed else "（未确认窗口）"),
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
        verification_detail="已读取可见窗口标题",
        message=f"可见窗口 {len(titles)} 个",
        data={"titles": titles, "count": len(titles)},
    )


def get_active_window(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    title = ctx.platform.foreground_title()
    return ToolResult(
        ok=True,
        verified=bool(title),
        verification_detail="已读取前台窗口",
        message=title or "没有前台窗口标题",
        data={"title": title},
        error=None if title else "没有前台窗口",
        error_code=None if title else "not_found",
    )


def focus_window(args: WindowTitleArgs, ctx: ToolContext) -> ToolResult:
    focused = bool(ctx.platform.focus_window(args.title))
    return ToolResult(
        ok=focused,
        verified=focused,
        verification_detail="前台窗口标题匹配" if focused else "没能把目标窗口放到前台",
        message=f"已聚焦 {args.title}" if focused else f"未找到窗口 {args.title}",
        error=None if focused else "窗口未就绪",
        error_code=None if focused else "window_not_ready",
    )


def close_application(args: WindowTitleArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("关闭应用必须经过这次操作的确认")
    closed = bool(ctx.platform.close_window(args.title))
    still_open = any(args.title.lower() in title.lower() for title in ctx.platform.window_titles())
    verified = closed and not still_open
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="窗口标题已消失" if verified else "关闭请求后窗口仍在或未找到",
        message=f"已请求关闭 {args.title}",
        error=None if verified else "未能确认窗口已关闭",
        error_code=None if verified else "verification_failed",
    )
