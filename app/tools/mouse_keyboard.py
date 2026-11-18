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
        raise PermissionError("键鼠操作必须经过这次动作的确认")


def _check_point(ctx: ToolContext, x: int, y: int) -> dict:
    bounds = ctx.platform.virtual_screen()
    if not point_inside(x, y, bounds):
        raise PermissionError(f"坐标 ({x}, {y}) 不在虚拟屏幕 {bounds} 内")
    return bounds


def _focus_if_requested(ctx: ToolContext, title: str) -> ToolResult | None:
    if not title:
        return None
    if not ctx.platform.focus_window(title):
        return ToolResult(ok=False, error="目标窗口未就绪，已取消键鼠操作", error_code="window_not_ready")
    foreground = ctx.platform.foreground_title()
    if title.lower() not in foreground.lower():
        return ToolResult(ok=False, error="前台窗口与目标不一致，已取消键鼠操作", error_code="window_not_ready")
    return None


def move_mouse(args: PointArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    bounds = _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.move_mouse(args.x, args.y)
    return ToolResult(ok=True, verified=True, verification_detail=f"坐标位于屏幕 {bounds}", message="已移动鼠标", data={"x": args.x, "y": args.y})


def preflight_named_click(args: NamedClickArgs, _ctx: ToolContext) -> Preflight:
    if args.pick == "first_video":
        impact = "将把鼠标移到 YouTube 窗口里的第一个视频并单击。不会输入文字。"
    else:
        impact = f"将把鼠标移到名称匹配“{args.name}”的可见控件中心并单击。不会输入文字。"
    return Preflight(summary="鼠标点击控件", impact=impact)


def click_named(args: NamedClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    label = " ".join(args.name.split())
    if args.pick not in {"", "first_video"}:
        return ToolResult(ok=False, error="不支持的点击方式", error_code="permission")
    if args.pick != "first_video" and (not label or len(label) > 120):
        return ToolResult(ok=False, error="控件名称无效", error_code="permission")
    if any(word in label.lower() for word in ("password", "passwd", "密码", "口令", "密钥")):
        raise PermissionError("不会用鼠标点击密码或密钥输入框")
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
            error=outcome.get("error") or "没有点到控件",
            error_code=outcome.get("error_code") or "window_not_ready",
            data=outcome,
        )
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"鼠标已点击“{outcome.get('name') or label}”",
        message=f"已用鼠标点击 {outcome.get('name') or label}",
        data={"x": outcome.get("x"), "y": outcome.get("y"), "name": outcome.get("name")},
    )


def click(args: ClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if args.button not in {"left", "right", "middle"}:
        return ToolResult(ok=False, error="不支持的鼠标按键", error_code="permission")
    bounds = _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, args.button, 1)
    return ToolResult(ok=True, verified=True, verification_detail=f"已在屏幕范围内点击 {bounds}", message="已点击", data={"x": args.x, "y": args.y})


def double_click(args: ClickArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, "left", 2)
    return ToolResult(ok=True, verified=True, verification_detail="双击坐标已校验", message="已双击", data={"x": args.x, "y": args.y})


def right_click(args: PointArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.x, args.y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.click(args.x, args.y, "right", 1)
    return ToolResult(ok=True, verified=True, verification_detail="右键坐标已校验", message="已右键点击", data={"x": args.x, "y": args.y})


def scroll(args: ScrollArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if not -20 <= args.amount <= 20:
        return ToolResult(ok=False, error="滚动量超出安全范围", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    if args.x is not None and args.y is not None:
        _check_point(ctx, args.x, args.y)
        ctx.platform.move_mouse(args.x, args.y)
    ctx.platform.scroll(args.amount)
    return ToolResult(ok=True, verified=True, verification_detail="滚动量在允许范围内", message="已滚动", data={"amount": args.amount})


def drag_and_drop(args: DragArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    _check_point(ctx, args.start_x, args.start_y)
    _check_point(ctx, args.end_x, args.end_y)
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.drag_drop((args.start_x, args.start_y), (args.end_x, args.end_y))
    return ToolResult(ok=True, verified=True, verification_detail="拖拽起止点都在屏幕内", message="已拖拽", data={})


def type_text(args: TypeArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    if not args.text or len(args.text) > 4000:
        return ToolResult(ok=False, error="文本为空或过长", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.type_text(args.text)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"已确认窗口“{args.window_title}”后输入 {len(args.text)} 个字符",
        message=f"已向 {args.window_title} 输入 {len(args.text)} 个字符",
        data={"length": len(args.text), "window_title": args.window_title},
    )


def press_key(args: KeyArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    key = args.key.lower()
    if key not in ALLOWED_KEYS:
        return ToolResult(ok=False, error="按键不在允许列表中", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.press_key(key)
    return ToolResult(ok=True, verified=True, verification_detail="按键属于允许列表", message=f"已按下 {key}", data={"key": key})


def hotkey(args: HotkeyArgs, ctx: ToolContext) -> ToolResult:
    _require_approval(ctx)
    keys = [key.lower() for key in args.keys]
    if not 1 <= len(keys) <= 3 or any(key not in ALLOWED_KEYS for key in keys):
        return ToolResult(ok=False, error="组合键不被允许", error_code="permission")
    blocked = _focus_if_requested(ctx, args.window_title)
    if blocked:
        return blocked
    ctx.platform.hotkey(keys)
    return ToolResult(ok=True, verified=True, verification_detail="组合键属于允许列表", message="已按下组合键", data={"keys": keys})


def get_mouse_position(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    x, y = ctx.platform.mouse_position()
    bounds = ctx.platform.virtual_screen()
    inside = point_inside(x, y, bounds)
    return ToolResult(
        ok=True,
        verified=inside,
        verification_detail="坐标位于虚拟屏幕内" if inside else "坐标超出虚拟屏幕",
        message=f"{x}, {y}",
        data={"x": x, "y": y, "bounds": bounds},
    )
