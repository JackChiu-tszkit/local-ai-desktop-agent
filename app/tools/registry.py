"""Approved tool registry. There is no shell or arbitrary-code tool."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from app.security.risk_classifier import BASE_RISK
from app.storage.models import ToolResult
from app.tools.base import ToolContext, ToolSpec
from app.tools.browser import UrlArgs, open_browser, open_url, preflight_browser, read_page_title
from app.tools.filesystem import (
    ApplyMovesArgs,
    CreateDirectoryArgs,
    CreateTextArgs,
    DuplicateArgs,
    FindFilesArgs,
    HashArgs,
    ListDirectoryArgs,
    MetadataArgs,
    OpenFileArgs,
    OrganizeArgs,
    RecycleArgs,
    RenameArgs,
    SpreadsheetArgs,
    TransferArgs,
    apply_moves,
    calculate_file_hash,
    copy_files,
    create_directory,
    create_spreadsheet,
    create_text_file,
    find_duplicates,
    find_files,
    get_file_metadata,
    list_directory,
    move_files,
    move_to_recycle_bin,
    open_file,
    preflight_apply,
    preflight_recycle,
    preflight_rename,
    preflight_spreadsheet,
    preflight_text,
    preflight_transfer,
    preview_organize,
    rename_file,
)
from app.tools.mouse_keyboard import (
    ClickArgs,
    DragArgs,
    HotkeyArgs,
    KeyArgs,
    NamedClickArgs,
    PointArgs,
    ScrollArgs,
    TypeArgs,
    click,
    click_named,
    double_click,
    drag_and_drop,
    get_mouse_position,
    hotkey,
    move_mouse,
    preflight_named_click,
    press_key,
    right_click,
    scroll,
    type_text,
)
from app.tools.mouse_keyboard import (
    EmptyArgs as MouseEmpty,
)
from app.tools.screen import AnalyzeArgs, CaptureArgs, analyze_screen, capture_screen, read_ui_tree
from app.tools.screen import EmptyArgs as ScreenEmpty
from app.tools.window_manager import (
    EmptyArgs as WindowEmpty,
)
from app.tools.window_manager import (
    LaunchArgs,
    WindowTitleArgs,
    close_application,
    focus_window,
    get_active_window,
    launch_app,
    list_windows,
)
from app.tools.windows_settings import (
    AppearanceArgs,
    SettingsArgs,
    WallpaperArgs,
    get_appearance,
    get_wallpaper,
    open_settings,
    preflight_appearance,
    preflight_wallpaper,
    set_appearance,
    set_wallpaper,
)
from app.tools.windows_settings import (
    EmptyArgs as SettingsEmpty,
)


def _spec(name: str, description: str, model: type[BaseModel], handler, preflight=None, granted: bool = False) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        args_model=model,
        handler=handler,
        risk=BASE_RISK[name],
        preflight=preflight,
        requires_granted_flag=granted,
    )


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def add(self, spec: ToolSpec) -> None:
        if spec.name in {"shell", "powershell", "cmd", "exec", "python", "delete_file", "permanent_delete"}:
            raise ValueError(f"Refusing to register tool {spec.name}")
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return sorted(self._tools)

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def schemas(self) -> list[dict]:
        items = []
        for spec in self._tools.values():
            items.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.args_model.model_json_schema(),
                }
            )
        return items

    def call(self, name: str, arguments: dict, ctx: ToolContext) -> tuple[BaseModel, ToolResult]:
        spec = self.get(name)
        try:
            model = spec.args_model.model_validate(arguments)
        except ValidationError as exc:
            return spec.args_model.model_construct(), ToolResult(ok=False, error=str(exc), error_code="permission")
        if spec.requires_granted_flag and not ctx.approved:
            raise PermissionError(f"{name} requires confirmation")
        result = spec.handler(model, ctx)
        return model, result

    def preflight(self, name: str, arguments: dict, ctx: ToolContext):
        spec = self.get(name)
        model = spec.args_model.model_validate(arguments)
        if spec.preflight is None:
            return None
        return spec.preflight(model, ctx)


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    specs = [
        _spec("find_files", "Search allowed folders by name, extension, size, and modification time", FindFilesArgs, find_files),
        _spec("list_directory", "List the immediate contents of an allowed folder", ListDirectoryArgs, list_directory),
        _spec("get_file_metadata", "Read file size and modification time", MetadataArgs, get_file_metadata),
        _spec("calculate_file_hash", "Calculate the SHA-256 of an ordinary file", HashArgs, calculate_file_hash),
        _spec("find_duplicates", "Find files with identical contents in one folder, without deleting", DuplicateArgs, find_duplicates),
        _spec("create_directory", "Create a directory inside the allowed scope", CreateDirectoryArgs, create_directory),
        _spec("create_text_file", "Write a text file", CreateTextArgs, create_text_file, preflight_text),
        _spec("create_spreadsheet", "Create an xlsx spreadsheet", SpreadsheetArgs, create_spreadsheet, preflight_spreadsheet),
        _spec("rename_file", "Rename a file", RenameArgs, rename_file, preflight_rename),
        _spec("copy_files", "Copy files into an allowed folder", TransferArgs, copy_files, preflight_transfer),
        _spec("move_files", "Move files into an allowed folder", TransferArgs, move_files, preflight_transfer),
        _spec("move_to_recycle_bin", "Move the specified files to the Recycle Bin", RecycleArgs, move_to_recycle_bin, preflight_recycle, True),
        _spec("preview_organize", "Preview a plan that organizes a folder by extension", OrganizeArgs, preview_organize),
        _spec("apply_moves", "Apply a move plan that was already previewed", ApplyMovesArgs, apply_moves, preflight_apply),
        _spec("open_file", "Open an ordinary file with its associated program", OpenFileArgs, open_file),
        _spec("launch_app", "Open Notepad, Calculator, Paint, or File Explorer", LaunchArgs, launch_app),
        _spec("list_windows", "List visible window titles", WindowEmpty, list_windows),
        _spec("get_active_window", "Read the foreground window title", WindowEmpty, get_active_window),
        _spec("focus_window", "Try to bring the window with a matching title to the foreground", WindowTitleArgs, focus_window),
        _spec("close_application", "Send a close message to the matching window", WindowTitleArgs, close_application, granted=True),
        _spec("move_mouse", "Move the mouse to a checked coordinate", PointArgs, move_mouse, granted=True),
        _spec("click", "Click a checked coordinate", ClickArgs, click, granted=True),
        _spec("click_named", "Move the mouse to a visible control with a matching name and click", NamedClickArgs, click_named, preflight_named_click, True),
        _spec("double_click", "Double-click a checked coordinate", ClickArgs, double_click, granted=True),
        _spec("right_click", "Right-click a checked coordinate", PointArgs, right_click, granted=True),
        _spec("scroll", "Scroll within the allowed range", ScrollArgs, scroll, granted=True),
        _spec("type_text", "Type text into a window that has been checked", TypeArgs, type_text, granted=True),
        _spec("press_key", "Press one allow-listed key", KeyArgs, press_key, granted=True),
        _spec("hotkey", "Press up to three allow-listed shortcut keys", HotkeyArgs, hotkey, granted=True),
        _spec("drag_and_drop", "Drag within the screen", DragArgs, drag_and_drop, granted=True),
        _spec("get_mouse_position", "Read the current mouse coordinate", MouseEmpty, get_mouse_position),
        _spec("capture_screen", "Save the screen into the local data directory", CaptureArgs, capture_screen, granted=True),
        _spec("read_ui_tree", "Read the accessibility controls of the current window", ScreenEmpty, read_ui_tree),
        _spec(
            "analyze_screen",
            "Describe the screen with a vision model when authorized; otherwise use only the accessibility tree",
            AnalyzeArgs,
            analyze_screen,
            granted=True,
        ),
        _spec("set_wallpaper", "Change the current user's desktop wallpaper", WallpaperArgs, set_wallpaper, preflight_wallpaper, True),
        _spec("get_wallpaper", "Read the current wallpaper path", SettingsEmpty, get_wallpaper),
        _spec("set_appearance", "Switch the current user's light or dark appearance", AppearanceArgs, set_appearance, preflight_appearance, True),
        _spec("get_appearance", "Read the current light or dark appearance", SettingsEmpty, get_appearance),
        _spec("open_settings", "Open an allow-listed Windows Settings page", SettingsArgs, open_settings),
        _spec("open_url", "Open an http or https address in the default browser", UrlArgs, open_url, granted=True),
        _spec("open_browser", "Open an http or https address in Chrome or Edge", UrlArgs, open_browser, preflight_browser, True),
        _spec("read_page_title", "Read only the page title when that is available", UrlArgs, read_page_title, granted=True),
    ]
    for spec in specs:
        registry.add(spec)
    return registry
