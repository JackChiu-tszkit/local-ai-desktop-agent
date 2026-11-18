"""Check the machine state after a tool returns."""

from __future__ import annotations

from pathlib import Path

from app.storage.models import ToolResult


def verify_step(tool: str, result: ToolResult) -> tuple[str, str]:
    if not result.ok:
        return "failed", result.error or "工具执行失败"
    if tool in {"open_file", "launch_app", "open_settings"} and result.data.get("confirmed") is False:
        return "warning", result.verification_detail or result.message
    if not result.verified:
        return "failed", result.verification_detail or "没有完成结果核对"
    for path in result.data.get("removed_sources") or []:
        if Path(path).exists():
            return "failed", f"核对失败，源路径仍存在: {path}"
    if tool == "move_to_recycle_bin":
        for path in result.data.get("targets") or []:
            if Path(path).exists():
                return "failed", f"核对失败，文件仍存在: {path}"
    for path in result.data.get("destinations") or []:
        if not Path(path).exists():
            return "failed", f"核对失败，目标不存在: {path}"
    for item in result.data.get("moved") or []:
        if isinstance(item, dict):
            if Path(item["src"]).exists() or not Path(item["dst"]).exists():
                return "failed", "核对失败，整理结果与磁盘不一致"
    destination = result.data.get("destination")
    if tool in {"create_text_file", "create_spreadsheet", "create_directory", "rename_file"} and destination:
        if not Path(destination).exists():
            return "failed", f"核对失败，目标不存在: {destination}"
    return "succeeded", result.verification_detail or result.message or "已核对"
