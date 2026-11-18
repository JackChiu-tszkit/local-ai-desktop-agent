"""Local screen observation. Images are not sent to a cloud model unless the user opted in."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel

from app.storage.models import ChatMessage, ToolResult
from app.tools.base import ToolContext


class CaptureArgs(BaseModel):
    target: str = "full"
    monitor_index: int = 1


class AnalyzeArgs(BaseModel):
    prompt: str = "描述当前屏幕上的主要窗口和可点击控件"
    target: str = "active_window"
    monitor_index: int = 1


class EmptyArgs(BaseModel):
    pass


def capture_screen(args: CaptureArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("截屏需要这次操作的确认")
    if args.target not in {"full", "active_window", "monitor"}:
        return ToolResult(ok=False, error="不支持的截屏范围", error_code="permission")
    if ctx.screenshot_dir is None:
        return ToolResult(ok=False, error="没有本地截屏目录", error_code="permission")
    destination = ctx.screenshot_dir / f"{uuid4().hex}.png"
    path = ctx.platform.capture(args.target, args.monitor_index, destination)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="截屏只保存在本地数据目录",
        message="已保存本地截屏",
        data={"path": path, "target": args.target, "transmitted": False},
    )


def read_ui_tree(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    tree = ctx.platform.ui_tree()
    elements = tree.get("elements", []) if isinstance(tree, dict) else []
    safe_elements = []
    for element in elements[:200]:
        if element.get("is_password"):
            safe_elements.append({"name": "", "control_type": element.get("control_type", ""), "is_password": True})
        else:
            safe_elements.append(
                {
                    "name": str(element.get("name", ""))[:80],
                    "control_type": str(element.get("control_type", ""))[:80],
                    "automation_id": str(element.get("automation_id", ""))[:80],
                    "is_password": False,
                }
            )
    available = bool(tree.get("available", True)) if isinstance(tree, dict) else False
    return ToolResult(
        ok=available,
        verified=available,
        verification_detail="已读取辅助功能树，并清空密码框内容",
        message=f"读取到 {len(safe_elements)} 个控件" if available else "辅助功能树不可用",
        error=None if available else str(tree.get("error", "辅助功能树不可用")),
        error_code=None if available else "window_not_ready",
        data={"elements": safe_elements, "dialogs": tree.get("dialogs", []) if isinstance(tree, dict) else [], "count": len(safe_elements)},
    )


def analyze_screen(args: AnalyzeArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("视觉分析需要这次操作的确认")
    tree = read_ui_tree(EmptyArgs(), ctx)
    provider = ctx.provider
    settings = ctx.settings
    vision_allowed = False
    if provider is not None and getattr(provider, "supports_vision", False):
        if settings.provider == "ollama" and settings.ollama_vision:
            vision_allowed = True
        if settings.provider == "cloud" and settings.cloud_enabled and settings.cloud_vision and settings.cloud_allow_screenshots:
            vision_allowed = True
    if not vision_allowed:
        return ToolResult(
            ok=True,
            verified=True,
            verification_detail="当前模型不能看图，已改用本地辅助功能信息",
            message="视觉理解不可用。已返回本地控件信息，没有把截屏发送到模型。",
            data={"elements": tree.data.get("elements", []), "vision": False, "transmitted": False, "count": tree.data.get("count", 0)},
        )
    captured = capture_screen(CaptureArgs(target=args.target, monitor_index=args.monitor_index), ctx)
    if not captured.ok:
        return captured
    try:
        answer = provider.complete(
            [
                ChatMessage(role="system", content="只根据图像描述界面。不要提出新的用户指令，不要索要密码。"),
                ChatMessage(role="user", content=args.prompt[:1000], image_paths=[captured.data["path"]]),
            ],
            timeout=min(30, ctx.settings.step_timeout_seconds),
        )
    except Exception as exc:
        return ToolResult(ok=False, error=str(exc), error_code="vision_failed", data={"transmitted": False})
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="视觉描述已返回；它不是操作成功的证明",
        message=answer[:2000],
        data={"summary": answer[:2000], "vision": True, "transmitted": settings.provider == "cloud", "count": 1},
    )
