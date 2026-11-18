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
    return Preflight(
        summary="Change the desktop wallpaper",
        paths=[str(path)],
        impact=f"The desktop wallpaper will change to {path}. This appearance change can be undone.",
    )


def set_wallpaper(args: WallpaperArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Changing the wallpaper requires confirmation for this action")
    path = ctx.guard.resolve(args.path, ctx.folders)
    if path.suffix.lower().lstrip(".") not in IMAGE_EXTENSIONS or not path.is_file():
        return ToolResult(ok=False, error="The wallpaper must be an existing image file", error_code="not_found")
    from PIL import Image

    with Image.open(path) as image:
        image.verify()
    applied = ctx.platform.set_wallpaper(str(path))
    current = ctx.platform.get_wallpaper()
    verified = Path(current).name.lower() == Path(applied).name.lower() or str(current).lower() == str(applied).lower()
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="Read the system wallpaper path back",
        message=f"Wallpaper set to {Path(applied).name}" if verified else "The wallpaper path read back from the system does not match",
        data={"source": str(path), "applied": applied, "current": current},
        error=None if verified else "Wallpaper verification failed",
        error_code=None if verified else "verification_failed",
    )


def get_wallpaper(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    current = ctx.platform.get_wallpaper()
    return ToolResult(ok=True, verified=True, verification_detail="Read the wallpaper path back", message=current, data={"path": current})


def preflight_appearance(args: AppearanceArgs, _ctx: ToolContext) -> Preflight:
    return Preflight(
        summary="Switch appearance",
        impact=f"Windows app and system appearance will switch to {args.mode}. This is a reversible setting for the current user.",
    )


def set_appearance(args: AppearanceArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Switching appearance requires confirmation for this action")
    mode = args.mode.lower()
    if mode not in {"light", "dark"}:
        return ToolResult(ok=False, error="Appearance can only be light or dark", error_code="permission")
    applied = ctx.platform.set_appearance(mode)
    verified = applied == mode
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="Read AppsUseLightTheme back",
        message=f"Appearance is {applied}",
        data={"mode": applied},
        error=None if verified else "Appearance verification failed",
        error_code=None if verified else "verification_failed",
    )


def get_appearance(_args: EmptyArgs, ctx: ToolContext) -> ToolResult:
    mode = ctx.platform.get_appearance()
    return ToolResult(
        ok=mode in {"light", "dark"},
        verified=mode in {"light", "dark"},
        verification_detail="Read the current user's appearance setting",
        message=mode,
        data={"mode": mode},
        error=None if mode in {"light", "dark"} else "Could not read the appearance",
    )


def open_settings(args: SettingsArgs, ctx: ToolContext) -> ToolResult:
    uri = SETTINGS_PAGES.get(args.page.strip().lower()) or SETTINGS_PAGES.get(args.page.strip())
    if uri is None:
        return ToolResult(ok=False, error="That Settings page is not allow-listed", error_code="permission")
    ctx.platform.open_settings(uri)
    confirmed = False
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        ctx.check_time()
        titles = " ".join(ctx.platform.window_titles()).lower()
        if "settings" in titles or "Settings" in titles:
            confirmed = True
            break
        time.sleep(0.15)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="Opened an allow-listed Settings page" if confirmed else "Requested Settings, but the window was not confirmed",
        message=f"Opened {uri}" if confirmed else f"Requested {uri} (window not confirmed)",
        data={"page": args.page, "uri": uri, "issued": True, "confirmed": confirmed},
    )
