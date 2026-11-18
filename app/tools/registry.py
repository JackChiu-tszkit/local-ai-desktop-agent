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
            raise ValueError(f"禁止注册工具 {spec.name}")
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
            raise PermissionError(f"{name} 必须经过确认")
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
        _spec("find_files", "按名称、扩展名、大小和修改时间搜索允许目录中的文件", FindFilesArgs, find_files),
        _spec("list_directory", "列出一个允许目录的直接内容", ListDirectoryArgs, list_directory),
        _spec("get_file_metadata", "读取文件大小和修改时间", MetadataArgs, get_file_metadata),
        _spec("calculate_file_hash", "计算普通文件的 SHA-256", HashArgs, calculate_file_hash),
        _spec("find_duplicates", "在一个目录内查找内容相同的文件，不删除", DuplicateArgs, find_duplicates),
        _spec("create_directory", "在允许范围内创建目录", CreateDirectoryArgs, create_directory),
        _spec("create_text_file", "写入一个文本文件", CreateTextArgs, create_text_file, preflight_text),
        _spec("create_spreadsheet", "创建一个 xlsx 表格", SpreadsheetArgs, create_spreadsheet, preflight_spreadsheet),
        _spec("rename_file", "重命名一个文件", RenameArgs, rename_file, preflight_rename),
        _spec("copy_files", "复制文件到允许的目录", TransferArgs, copy_files, preflight_transfer),
        _spec("move_files", "移动文件到允许的目录", TransferArgs, move_files, preflight_transfer),
        _spec("move_to_recycle_bin", "把指定文件移动到回收站", RecycleArgs, move_to_recycle_bin, preflight_recycle, True),
        _spec("preview_organize", "预览按扩展名整理目录的移动计划", OrganizeArgs, preview_organize),
        _spec("apply_moves", "执行已经预览过的移动计划", ApplyMovesArgs, apply_moves, preflight_apply),
        _spec("open_file", "用系统关联程序打开一个普通文件", OpenFileArgs, open_file),
        _spec("launch_app", "打开记事本、计算器、画图或资源管理器", LaunchArgs, launch_app),
        _spec("list_windows", "列出可见窗口标题", WindowEmpty, list_windows),
        _spec("get_active_window", "读取前台窗口标题", WindowEmpty, get_active_window),
        _spec("focus_window", "尝试把标题匹配的窗口放到前台", WindowTitleArgs, focus_window),
        _spec("close_application", "向匹配窗口发送关闭消息", WindowTitleArgs, close_application, granted=True),
        _spec("move_mouse", "移动鼠标到校验过的坐标", PointArgs, move_mouse, granted=True),
        _spec("click", "在校验过的坐标单击", ClickArgs, click, granted=True),
        _spec("click_named", "把鼠标移到名称匹配的可见控件并单击", NamedClickArgs, click_named, preflight_named_click, True),
        _spec("double_click", "在校验过的坐标双击", ClickArgs, double_click, granted=True),
        _spec("right_click", "在校验过的坐标右击", PointArgs, right_click, granted=True),
        _spec("scroll", "在允许范围内滚动滚轮", ScrollArgs, scroll, granted=True),
        _spec("type_text", "向已经核对的窗口输入文本", TypeArgs, type_text, granted=True),
        _spec("press_key", "按下允许列表中的一个键", KeyArgs, press_key, granted=True),
        _spec("hotkey", "按下最多三个允许的组合键", HotkeyArgs, hotkey, granted=True),
        _spec("drag_and_drop", "在屏幕范围内拖拽", DragArgs, drag_and_drop, granted=True),
        _spec("get_mouse_position", "读取当前鼠标坐标", MouseEmpty, get_mouse_position),
        _spec("capture_screen", "把屏幕保存到本地数据目录", CaptureArgs, capture_screen, granted=True),
        _spec("read_ui_tree", "读取当前窗口的辅助功能控件", ScreenEmpty, read_ui_tree),
        _spec("analyze_screen", "在获得授权时用视觉模型描述屏幕，否则只用辅助功能树", AnalyzeArgs, analyze_screen, granted=True),
        _spec("set_wallpaper", "更换当前用户的桌面壁纸", WallpaperArgs, set_wallpaper, preflight_wallpaper, True),
        _spec("get_wallpaper", "读取当前壁纸路径", SettingsEmpty, get_wallpaper),
        _spec("set_appearance", "切换当前用户的浅色或深色外观", AppearanceArgs, set_appearance, preflight_appearance, True),
        _spec("get_appearance", "读取当前浅色或深色外观", SettingsEmpty, get_appearance),
        _spec("open_settings", "打开一个允许的 Windows 设置页面", SettingsArgs, open_settings),
        _spec("open_url", "用默认浏览器打开一个 http 或 https 网址", UrlArgs, open_url, granted=True),
        _spec("open_browser", "用 Chrome 或 Edge 打开一个 http 或 https 网址", UrlArgs, open_browser, preflight_browser, True),
        _spec("read_page_title", "在可用时只读取网页标题", UrlArgs, read_page_title, granted=True),
    ]
    for spec in specs:
        registry.add(spec)
    return registry
