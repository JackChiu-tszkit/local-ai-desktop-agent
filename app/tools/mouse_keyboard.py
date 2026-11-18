"""Mouse and keyboard tools. Coordinates are checked against the virtual screen."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.platform.winlib import point_inside
from app.storage.models import Preflight, ToolResult
from app.tools.base import ToolContext

ALLOWED_KEYS = {
    "enter",
    "tab",
    "esc",
    "escape",
    "backspace",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
    "pageup",
    "pagedown",
    "space",
    "ctrl",
    "alt",
    "shift",
    "win",
    *{f"f{index}" for index in range(1, 13)},
    *{chr(code) for code in range(ord("a"), ord("z") + 1)},
    *{str(digit) for digit in range(10)},
}


class PointArgs(BaseModel):
    x: int
    y: int
    window_title: str = ""


class ClickArgs(PointArgs):
    button: str = "left"


class DragArgs(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    window_title: str = ""


class ScrollArgs(BaseModel):
    amount: int
    window_title: str = ""
    x: int | None = None
    y: int | None = None


class TypeArgs(BaseModel):
    text: str
    window_title: str = ""


class KeyArgs(BaseModel):
    key: str
    window_title: str = ""


class HotkeyArgs(BaseModel):
    keys: list[str] = Field(default_factory=list)
    window_title: str = ""


class NamedClickArgs(BaseModel):
    name: str = ""
    window_title: str = ""
    pick: str = ""


class EmptyArgs(BaseModel):
    pass


def _require_approval(ctx: ToolContext) -> None:
    if not ctx.approved:
        raise PermissionError("Mouse and keyboard actions require confirmation for this action")


def _check_point(ctx: ToolContext, x: int, y: int) -> dict:
    bounds = ctx.platform.virtual_screen()
    if not point_inside(x, y, bounds):
        raise PermissionError(f"Coordinate ({x}, {y}) is outside the virtual screen {bounds}")
    return bounds


def _focus_if_requested(ctx: ToolContext, title: str) -> ToolResult | None:
    if not title:
        return None
    if not ctx.platform.focus_window(title):
        return ToolResult(ok=False, error="The target window was not ready, so the pointer action was cancelled", error_code="window_not_ready")
    foreground = ctx.platform.foreground_title()
    if title.lower() not in foreground.lower():
        return ToolResult(ok=False, error="The foreground window did not match the target, so the pointer action was cancelled", error_code="window_not_ready")
    return None


def move_mouse(args: PointArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    bounds = _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.move_mouse(args.x, args.y)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"The coordinate is on screen {bounds}",
        message="The mouse moved",
        data={"x": args.x, "y": args.y},
    )


def preflight_named_click(args: NamedClickArgs, _ctx: ToolContext) -> Preflight:
    if args.pick == "first_video":
        impact = "The mouse will move to the first video in the YouTube window and click once. No text will be typed."
    else:
        impact = f"The mouse will move to the center of the visible control named '{args.name}' and click once. No text will be typed."
    return Preflight(summary="Click a control", impact=impact)


def click_named(args: NamedClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    label = " ".join(args.name.split())
    if args.pick not in {"", "first_video"}:
        return ToolResult(ok=False, error="That click method is not supported", error_code="permission")
    if args.pick != "first_video" and (not label or len(label) > 120):
        return ToolResult(ok=False, error="The control name is invalid", error_code="permission")
    if any(word in label.lower() for word in ("password", "passwd", "secret", "token")):
        raise PermissionError("The mouse will not click a password or secret field")
    ctx.step_deadline = ctx.task_deadline
    outcome = ctx.platform.click_named(
        label,
        args.window_title.strip(),
        ctx.cancel_event,
        ctx.task_deadline,
        pick=args.pick,
    )
    if not outcome.get("ok"):
        return ToolResult(
            ok=False,
            error=outcome.get("error") or "The control was not clicked",
            error_code=outcome.get("error_code") or "window_not_ready",
            data=outcome,
        )
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"The mouse clicked '{outcome.get('name') or label}'",
        message=f"Clicked {outcome.get('name') or label}",
        data={"x": outcome.get("x"), "y": outcome.get("y"), "name": outcome.get("name")},
    )


def click(args: ClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if args.button not in {"left", "right", "middle"}:
        return ToolResult(ok=False, error="That mouse button is not supported", error_code="permission")
    bounds = _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, args.button, 1)
    return ToolResult(ok=True, verified=True, verification_detail=f"Clicked inside the screen at {bounds}", message="Clicked", data={"x": args.x, "y": args.y})


def double_click(args: ClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, "left", 2)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="The double-click coordinate was checked",
        message="Double-clicked",
        data={"x": args.x, "y": args.y},
    )


def right_click(args: PointArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, "right", 1)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="The right-click coordinate was checked",
        message="Right-clicked",
        data={"x": args.x, "y": args.y},
    )


def scroll(args: ScrollArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if not -20 <= args.amount <= 20:
        return ToolResult(ok=False, error="The scroll amount is outside the safe range", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    if args.x is not None and args.y is not None:
        _check_point(ctx, args.x, args.y)
        ctx.platform.move_mouse(args.x, args.y)
    ctx.platform.scroll(args.amount)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="The scroll amount is within the allowed range",
        message="Scrolled",
        data={"amount": args.amount},
    )


def drag_and_drop(args: DragArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.start_x, args.start_y)
    _check_point(ctx, args.end_x, args.end_y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.drag_drop((args.start_x, args.start_y), (args.end_x, args.end_y))
    return ToolResult(ok=True, verified=True, verification_detail="Both drag points are on screen", message="Dragged", data={})


def type_text(args: TypeArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if not args.text or len(args.text) > 4000:
        return ToolResult(ok=False, error="The text is empty or too long", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.type_text(args.text)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"After confirming the window '{args.window_title}', typed {len(args.text)} characters",
        message=f"Typed into {args.window_title} {len(args.text)} characters",
        data={"length": len(args.text), "window_title": args.window_title},
    )


def press_key(args: KeyArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    key = args.key.lower()
    if key not in ALLOWED_KEYS:
        return ToolResult(ok=False, error="That key is not allow-listed", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.press_key(key)
    return ToolResult(ok=True, verified=True, verification_detail="The key is allow-listed", message=f"Pressed {key}", data={"key": key})


def hotkey(args: HotkeyArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    keys = [key.lower() for key in args.keys]
    if not 1 <= len(keys) <= 3 or any(key not in ALLOWED_KEYS for key in keys):
        return ToolResult(ok=False, error="That shortcut is not allowed", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.hotkey(keys)
    return ToolResult(ok=True, verified=True, verification_detail="The shortcut is allow-listed", message="Pressed the shortcut", data={"keys": keys})


def get_mouse_position(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    x, y = ctx.platform.mouse_position()
    bounds = ctx.platform.virtual_screen()
    inside = point_inside(x, y, bounds)
    return ToolResult(
        ok=True,
        verified=inside,
        verification_detail="The coordinate is inside the virtual screen" if inside else "The coordinate is outside the virtual screen",
        message=f"{x}, {y}",
        data={"x": x, "y": y, "bounds": bounds},
    )
