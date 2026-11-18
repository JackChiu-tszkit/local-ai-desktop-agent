"""Risk policy. The model cannot lower a risk level or skip confirmation."""

from __future__ import annotations

from typing import Any

from app.storage.models import Preflight, RiskDecision, RiskLevel

BASE_RISK: dict[str, RiskLevel] = {
    "find_files": RiskLevel.low,
    "list_directory": RiskLevel.low,
    "get_file_metadata": RiskLevel.low,
    "calculate_file_hash": RiskLevel.low,
    "find_duplicates": RiskLevel.low,
    "preview_organize": RiskLevel.low,
    "list_windows": RiskLevel.low,
    "get_active_window": RiskLevel.low,
    "get_mouse_position": RiskLevel.low,
    "read_ui_tree": RiskLevel.low,
    "get_wallpaper": RiskLevel.low,
    "get_appearance": RiskLevel.low,
    "open_file": RiskLevel.low,
    "launch_app": RiskLevel.low,
    "open_settings": RiskLevel.low,
    "focus_window": RiskLevel.low,
    "create_directory": RiskLevel.medium,
    "create_text_file": RiskLevel.medium,
    "create_spreadsheet": RiskLevel.medium,
    "rename_file": RiskLevel.medium,
    "copy_files": RiskLevel.medium,
    "move_files": RiskLevel.medium,
    "apply_moves": RiskLevel.medium,
    "set_wallpaper": RiskLevel.medium,
    "set_appearance": RiskLevel.medium,
    "move_mouse": RiskLevel.medium,
    "click": RiskLevel.medium,
    "click_named": RiskLevel.medium,
    "double_click": RiskLevel.medium,
    "right_click": RiskLevel.medium,
    "scroll": RiskLevel.medium,
    "type_text": RiskLevel.medium,
    "press_key": RiskLevel.medium,
    "hotkey": RiskLevel.medium,
    "drag_and_drop": RiskLevel.medium,
    "capture_screen": RiskLevel.medium,
    "analyze_screen": RiskLevel.medium,
    "open_url": RiskLevel.medium,
    "open_browser": RiskLevel.medium,
    "read_page_title": RiskLevel.medium,
    "move_to_recycle_bin": RiskLevel.high,
    "close_application": RiskLevel.high,
}

ALWAYS_CONFIRM = {
    "move_to_recycle_bin",
    "close_application",
    "set_wallpaper",
    "set_appearance",
    "move_mouse",
    "click",
    "click_named",
    "double_click",
    "right_click",
    "scroll",
    "type_text",
    "press_key",
    "hotkey",
    "drag_and_drop",
    "capture_screen",
    "analyze_screen",
    "open_url",
    "open_browser",
    "read_page_title",
}

BATCH_TOOLS = {"move_files", "copy_files", "apply_moves", "move_to_recycle_bin"}


def _target_count(arguments: dict[str, Any], preflight: Preflight | None) -> int:
    if preflight and preflight.paths:
        return len(preflight.paths)
    for key in ("paths", "operations", "sources"):
        value = arguments.get(key)
        if isinstance(value, list):
            return len(value)
    if arguments.get("source") or arguments.get("path"):
        return 1
    return 0


def classify(tool: str, arguments: dict[str, Any], preflight: Preflight | None = None) -> RiskDecision:
    known = tool in BASE_RISK
    risk = BASE_RISK.get(tool, RiskLevel.high)
    reasons: list[str] = []
    requires = False
    if not known or tool.startswith("mcp."):
        risk = RiskLevel.high
        requires = True
        reasons.append("Unknown or external tools are high risk and apply only to this preview")
    if tool in ALWAYS_CONFIRM:
        requires = True
        reasons.append("This action needs you to confirm this specific target once")
    if preflight and preflight.will_overwrite:
        risk = RiskLevel.high
        requires = True
        reasons.append("The target already exists and is overwritten only after confirmation")
    count = _target_count(arguments, preflight)
    if tool in BATCH_TOOLS and count > 1:
        requires = True
        reasons.append(f"This action affects {count} paths")
    if tool == "apply_moves" and count >= 1:
        requires = True
        reasons.append("Files will be moved along the paths in the preview")
    if tool in {"rename_file", "move_files", "copy_files"} and count > 3:
        requires = True
    if risk == RiskLevel.high:
        requires = True
    if requires and not reasons:
        reasons.append("This runs only after confirmation")
    return RiskDecision(risk=risk, requires_approval=requires, reasons=reasons)
