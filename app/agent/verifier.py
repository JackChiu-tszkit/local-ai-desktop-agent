"""Check the machine state after a tool returns."""

from __future__ import annotations

from pathlib import Path

from app.storage.models import ToolResult


def verify_step(tool: str, result: ToolResult) -> tuple[str, str]:
    if not result.ok:
        return "failed", result.error or "The tool failed"
    if tool in {"open_file", "launch_app", "open_settings"} and result.data.get("confirmed") is False:
        return "warning", result.verification_detail or result.message
    if not result.verified:
        return "failed", result.verification_detail or "The result was not verified"
    for path in result.data.get("removed_sources") or []:
        if Path(path).exists():
            return "failed", f"Verification failed. The source path still exists: {path}"
    if tool == "move_to_recycle_bin":
        for path in result.data.get("targets") or []:
            if Path(path).exists():
                return "failed", f"Verification failed. The file still exists: {path}"
    for path in result.data.get("destinations") or []:
        if not Path(path).exists():
            return "failed", f"Verification failed. The destination does not exist: {path}"
    for item in result.data.get("moved") or []:
        if isinstance(item, dict):
            if Path(item["src"]).exists() or not Path(item["dst"]).exists():
                return "failed", "Verification failed. The organized files do not match the disk"
    destination = result.data.get("destination")
    if tool in {"create_text_file", "create_spreadsheet", "create_directory", "rename_file"} and destination:
        if not Path(destination).exists():
            return "failed", f"Verification failed. The destination does not exist: {destination}"
    return "succeeded", result.verification_detail or result.message or "Verified"
