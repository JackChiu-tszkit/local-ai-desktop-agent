"""Documented user-level Windows appearance settings. No UAC prompt and no privilege elevation."""

from __future__ import annotations

import time
from pathlib import Path

from pydantic import BaseModel

from app.storage.models import Preflight, ToolResult
from app.tools.base import ToolContext
from app.tools.filesystem import IMAGE_EXTENSIONS

SETTINGS_PAGES = {
    "home": "ms-settings:",
    "system": "ms-settings:system",
    "display": "ms-settings:display",
    "personalization": "ms-settings:personalization",
    "colors": "ms-settings:colors",
    "apps": "ms-settings:appsfeatures",
    "storage": "ms-settings:storagesense",
    "主页": "ms-settings:",
    "系统": "ms-settings:system",
    "显示": "ms-settings:display",
    "个性化": "ms-settings:personalization",
    "颜色": "ms-settings:colors",
    "应用": "ms-settings:appsfeatures",
    "存储": "ms-settings:storagesense",
}


class WallpaperArgs(BaseModel):
    path: str


class AppearanceArgs(BaseModel):
    mode: str


class SettingsArgs(BaseModel):
    page: str = "home"


class EmptyArgs(BaseModel):
    pass


def preflight_wallpaper(args: WallpaperArgs, ctx: ToolContext) -> Preflight:
    path = ctx.guard.resolve(args.path, ctx.folders)
    return Preflight(summary="更换桌面壁纸", paths=[str(path)], impact=f"桌面壁纸会换成 {path}。这是可恢复的外观更改。")


def set_wallpaper(args: WallpaperArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("更换壁纸需要这次操作的确认")
    path = ctx.guard.resolve(args.path, ctx.folders)
    if path.suffix.lower().lstrip(".") not in IMAGE_EXTENSIONS or not path.is_file():
        return ToolResult(ok=False, error="壁纸必须是现有的图片文件", error_code="not_found")
    from PIL import Image

    with Image.open(path) as image:
        image.verify()
    applied = ctx.platform.set_wallpaper(str(path))
    current = ctx.platform.get_wallpaper()
    verified = Path(current).name.lower() == Path(applied).name.lower() or str(current).lower() == str(applied).lower()
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="已回读系统壁纸路径",
        message=f"壁纸已设为 {Path(applied).name}" if verified else "系统回读的壁纸路径与设置不一致",
        data={"source": str(path), "applied": applied, "current": current},
        error=None if verified else "壁纸核对失败",
        error_code=None if verified else "verification_failed",
    )


def get_wallpaper(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    current = ctx.platform.get_wallpaper()
    return ToolResult(ok=True, verified=True, verification_detail="已回读壁纸路径", message=current, data={"path": current})


def preflight_appearance(args: AppearanceArgs, _ctx: ToolContext) -> Preflight:
    return Preflight(summary="切换外观", impact=f"Windows 应用和系统外观会切换为 {args.mode}。这是当前用户的可恢复设置。")


def set_appearance(args: AppearanceArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("切换外观需要这次操作的确认")
    mode = args.mode.lower()
    if mode not in {"light", "dark"}:
        return ToolResult(ok=False, error="外观只能是 light 或 dark", error_code="permission")
    applied = ctx.platform.set_appearance(mode)
    verified = applied == mode
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="已回读 AppsUseLightTheme",
        message=f"外观为 {applied}",
        data={"mode": applied},
        error=None if verified else "外观核对失败",
        error_code=None if verified else "verification_failed",
    )


def get_appearance(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    mode = ctx.platform.get_appearance()
    return ToolResult(
        ok=mode in {"light", "dark"},
        verified=mode in {"light", "dark"},
        verification_detail="已读取当前用户外观设置",
        message=mode,
        data={"mode": mode},
        error=None if mode in {"light", "dark"} else "无法读取外观",
    )


def open_settings(args: SettingsArgs, ctx: ToolContext) -> ToolResult:
    uri = SETTINGS_PAGES.get(args.page.strip().lower()) or SETTINGS_PAGES.get(args.page.strip())
    if uri is None:
        return ToolResult(ok=False, error="设置页面不在允许列表中", error_code="permission")
    ctx.platform.open_settings(uri)
    confirmed = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        ctx.check_time()
        titles = " ".join(ctx.platform.window_titles()).lower()
        if "settings" in titles or "设置" in titles:
            confirmed = True
            break
        time.sleep(0.15)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="已打开允许列表中的设置页面" if confirmed else "已请求打开设置，但未确认窗口",
        message=f"已打开 {uri}" if confirmed else f"已请求打开 {uri}（窗口未确认）",
        data={"page": args.page, "uri": uri, "issued": True, "confirmed": confirmed},
    )
