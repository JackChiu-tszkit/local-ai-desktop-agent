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
    prompt: str = "Describe the main windows and clickable controls on the current screen"
    target: str = "active_window"
    monitor_index: int = 1


class EmptyArgs(BaseModel):
    pass


def capture_screen(args: CaptureArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("A screenshot requires confirmation for this action")
    if args.target not in {"full", "active_window", "monitor"}:
        return ToolResult(ok=False, error="That screenshot target is not supported", error_code="permission")
    if ctx.screenshot_dir is None:
        return ToolResult(ok=False, error="There is no local screenshot directory", error_code="permission")
    destination = ctx.screenshot_dir / f"{uuid4().hex}.png"
    path = ctx.platform.capture(args.target, args.monitor_index, destination)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="The screenshot is stored only in the local data directory",
        message="Saved a local screenshot",
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
        verification_detail="Read the accessibility tree and cleared password fields",
        message=f"Read {len(safe_elements)} controls" if available else "The accessibility tree is unavailable",
        error=None if available else str(tree.get("error", "The accessibility tree is unavailable")),
        error_code=None if available else "window_not_ready",
        data={"elements": safe_elements, "dialogs": tree.get("dialogs", []) if isinstance(tree, dict) else [], "count": len(safe_elements)},
    )


def analyze_screen(args: AnalyzeArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Vision analysis requires confirmation for this action")
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
            verification_detail="The current model cannot see images, so local accessibility information was used instead",
            message="Vision is unavailable. Local control information was returned, and the screenshot was not sent to a model.",
            data={"elements": tree.data.get("elements", []), "vision": False, "transmitted": False, "count": tree.data.get("count", 0)},
        )
    captured = capture_screen(CaptureArgs(target=args.target, monitor_index=args.monitor_index), ctx)
    if not captured.ok:
        return captured
    try:
        answer = provider.complete(
            [
                ChatMessage(role="system", content="Describe the interface from the image only. Do not invent a new user instruction or ask for a password."),
                ChatMessage(role="user", content=args.prompt[:1000], image_paths=[captured.data["path"]]),
            ],
            timeout=min(30, ctx.settings.step_timeout_seconds),
        )
    except Exception as exc:
        return ToolResult(ok=False, error=str(exc), error_code="vision_failed", data={"transmitted": False})
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="A visual description was returned. It is not proof that an action succeeded.",
        message=answer[:2000],
        data={"summary": answer[:2000], "vision": True, "transmitted": settings.provider == "cloud", "count": 1},
    )
