"""Filesystem tools. Permanent deletion is intentionally not implemented."""

from __future__ import annotations

import hashlib
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, Field

from app.security.permissions import is_secret_path
from app.storage.models import Preflight, ToolResult
from app.tools.base import ToolContext

SKIP_DIRS = {
    "$recycle.bin",
    "system volume information",
    "node_modules",
    ".git",
    "appdata",
    "__pycache__",
}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp", "gif"}
MAX_BATCH = 300


class FindFilesArgs(BaseModel):
    root: str | None = None
    name: str | None = None
    name_contains: str | None = None
    extension: str | None = None
    extensions: list[str] = Field(default_factory=list)
    min_size: int | None = None
    max_size: int | None = None
    modified_after: str | None = None
    modified_before: str | None = None
    modified_within_days: int | None = None
    max_results: int = 100


class ListDirectoryArgs(BaseModel):
    path: str


class MetadataArgs(BaseModel):
    path: str


class HashArgs(BaseModel):
    path: str


class DuplicateArgs(BaseModel):
    root: str
    max_depth: int = 4


class CreateDirectoryArgs(BaseModel):
    path: str


class CreateTextArgs(BaseModel):
    path: str
    content: str


class RenameArgs(BaseModel):
    source: str
    new_name: str


class TransferArgs(BaseModel):
    paths: list[str]
    destination_directory: str


class RecycleArgs(BaseModel):
    paths: list[str]


class OrganizeArgs(BaseModel):
    root: str


class ApplyMovesArgs(BaseModel):
    operations: list[dict]


class OpenFileArgs(BaseModel):
    path: str


class SpreadsheetArgs(BaseModel):
    path: str
    headers: list[str] = Field(default_factory=lambda: ["日期", "类别", "金额", "备注"])
    rows: list[list[str]] = Field(default_factory=list)


def _normalize_ext(value: str) -> str:
    return value.lower().lstrip(".")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _safe_name(name: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' else char for char in name).strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        raise PermissionError("文件名无效")
    return cleaned


def _metadata(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "is_dir": path.is_dir(),
        "sensitive": is_secret_path(path),
    }


def _reject_secret(path: Path, action: str) -> None:
    if is_secret_path(path):
        raise PermissionError(f"已拒绝{action}敏感文件: {path.name}")


def _roots(args_root: str | None, ctx: ToolContext) -> list[Path]:
    if args_root:
        return [ctx.guard.resolve(args_root, ctx.folders)]
    return [path for path in ctx.folders.values()]


def _walk_files(root: Path, ctx: ToolContext, max_depth: int):
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        ctx.check_time()
        current = Path(dirpath)
        try:
            depth = len(current.resolve().relative_to(root.resolve()).parts)
        except ValueError:
            dirnames[:] = []
            continue
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [name for name in dirnames if name.lower() not in SKIP_DIRS]
        for filename in filenames:
            yield current / filename


def find_files(args: FindFilesArgs, ctx: ToolContext) -> ToolResult:
    extensions = {_normalize_ext(item) for item in args.extensions if item}
    if args.extension:
        extensions.add(_normalize_ext(args.extension))
    after = _parse_time(args.modified_after) if args.modified_after else None
    before = _parse_time(args.modified_before) if args.modified_before else None
    if args.modified_within_days is not None:
        after = datetime.now() - timedelta(days=args.modified_within_days)
    limit = max(1, min(args.max_results, ctx.max_results, 500))
    matches: list[dict] = []
    truncated = False
    for root in _roots(args.root, ctx):
        if not root.exists():
            continue
        for path in _walk_files(root, ctx, max_depth=8):
            if not path.is_file() or path.is_symlink():
                continue
            name = path.name.lower()
            if args.name and name != args.name.lower():
                continue
            if args.name_contains and args.name_contains.lower() not in name:
                continue
            if extensions and path.suffix.lower().lstrip(".") not in extensions:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if args.min_size is not None and stat.st_size < args.min_size:
                continue
            if args.max_size is not None and stat.st_size > args.max_size:
                continue
            modified = datetime.fromtimestamp(stat.st_mtime)
            if after and modified < after:
                continue
            if before and modified > before:
                continue
            matches.append(_metadata(path))
            if len(matches) >= limit:
                truncated = True
                break
        if truncated:
            break
    matches.sort(key=lambda item: item["modified"], reverse=True)
    missing = [item["path"] for item in matches if not Path(item["path"]).exists()]
    if missing:
        return ToolResult(ok=False, error="搜索结果未能核对", error_code="verification_failed")
    latest = matches[0]["path"] if matches else None
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"已核对 {len(matches)} 个路径存在",
        message=f"找到 {len(matches)} 个文件" + ("，结果已截断" if truncated else ""),
        data={"matches": matches, "count": len(matches), "latest": latest, "truncated": truncated},
    )


def list_directory(args: ListDirectoryArgs, ctx: ToolContext) -> ToolResult:
    path = ctx.guard.resolve(args.path, ctx.folders)
    if not path.is_dir():
        return ToolResult(ok=False, error="目录不存在", error_code="not_found")
    entries = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.lower())[:500]:
        ctx.check_time()
        if child.is_symlink():
            continue
        try:
            entries.append(_metadata(child))
        except OSError:
            continue
    names = "、".join(item["name"] for item in entries[:20])
    return ToolResult(
        ok=True,
        verified=path.exists(),
        verification_detail="目录存在",
        message=f"{path} 中有 {len(entries)} 个条目: {names}",
        data={"path": str(path), "entries": entries, "count": len(entries)},
    )


def get_file_metadata(args: MetadataArgs, ctx: ToolContext) -> ToolResult:
    path = ctx.guard.resolve(args.path, ctx.folders)
    if not path.exists():
        return ToolResult(ok=False, error="文件不存在", error_code="not_found")
    data = _metadata(path)
    return ToolResult(ok=True, verified=True, verification_detail="已读取元数据", message=path.name, data=data)


def calculate_file_hash(args: HashArgs, ctx: ToolContext) -> ToolResult:
    path = ctx.guard.resolve(args.path, ctx.folders)
    _reject_secret(path, "计算")
    if not path.is_file():
        return ToolResult(ok=False, error="不是文件", error_code="not_found")
    if path.stat().st_size > ctx.max_hash_bytes:
        return ToolResult(ok=False, error="文件超过哈希大小限制", error_code="too_large")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            ctx.check_time()
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    value = digest.hexdigest()
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="已完成 SHA-256",
        message=value,
        data={"path": str(path), "sha256": value, "size": path.stat().st_size},
    )


def find_duplicates(args: DuplicateArgs, ctx: ToolContext) -> ToolResult:
    root = ctx.guard.resolve(args.root, ctx.folders)
    groups: dict[int, list[Path]] = {}
    scanned = 0
    skipped_large = 0
    for path in _walk_files(root, ctx, max_depth=max(1, args.max_depth)):
        if not path.is_file() or path.is_symlink() or is_secret_path(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        scanned += 1
        if scanned > 5000:
            break
        if size > ctx.max_hash_bytes:
            skipped_large += 1
            continue
        groups.setdefault(size, []).append(path)
    duplicates = []
    for size, paths in groups.items():
        if len(paths) < 2:
            continue
        hashed: dict[str, list[str]] = {}
        for path in paths:
            ctx.check_time()
            digest = hashlib.sha256()
            try:
                with path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
            except OSError:
                continue
            hashed.setdefault(digest.hexdigest(), []).append(str(path))
        for fingerprint, items in hashed.items():
            if len(items) > 1:
                duplicates.append({"hash": fingerprint, "size": size, "paths": items})
    lines = []
    for group in duplicates[:20]:
        lines.append("、".join(group["paths"]))
    summary = f"发现 {len(duplicates)} 组重复文件"
    if lines:
        summary = summary + "\n" + "\n".join(lines)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="只生成重复项报告，没有删除文件",
        message=summary,
        data={"groups": duplicates, "scanned": scanned, "skipped_large": skipped_large, "count": len(duplicates)},
    )


def create_directory(args: CreateDirectoryArgs, ctx: ToolContext) -> ToolResult:
    path = ctx.guard.resolve(args.path, ctx.folders)
    if path.exists() and not path.is_dir():
        return ToolResult(ok=False, error="同名文件已存在", error_code="exists")
    path.mkdir(parents=True, exist_ok=True)
    verified = path.is_dir()
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="目录已存在" if verified else "目录创建后仍不存在",
        message=f"目录已准备: {path}",
        data={"path": str(path)},
        error=None if verified else "未能核对目录",
    )


def _preflight_write(path: Path, summary: str) -> Preflight:
    return Preflight(
        summary=summary,
        paths=[str(path)],
        will_overwrite=path.exists(),
        impact=f"将写入 {path}" + ("，并覆盖现有文件" if path.exists() else ""),
    )


def preflight_text(args: CreateTextArgs, ctx: ToolContext) -> Preflight:
    return _preflight_write(ctx.guard.resolve(args.path, ctx.folders), "创建文本文件")


def create_text_file(args: CreateTextArgs, ctx: ToolContext) -> ToolResult:
    if len(args.content) > 100_000:
        return ToolResult(ok=False, error="文本过长", error_code="too_large")
    path = ctx.guard.resolve(args.path, ctx.folders)
    _reject_secret(path, "写入")
    if path.exists() and not ctx.approved:
        raise PermissionError("覆盖文件需要确认")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args.content, encoding="utf-8")
    verified = path.is_file() and path.read_text(encoding="utf-8") == args.content
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="已回读文件内容",
        message=f"已写入 {path}",
        data={"path": str(path), "destination": str(path)},
        error=None if verified else "写入后的内容核对失败",
    )


def preflight_spreadsheet(args: SpreadsheetArgs, ctx: ToolContext) -> Preflight:
    return _preflight_write(ctx.guard.resolve(args.path, ctx.folders), "创建表格")


def create_spreadsheet(args: SpreadsheetArgs, ctx: ToolContext) -> ToolResult:
    from openpyxl import Workbook

    if len(args.rows) > 500:
        return ToolResult(ok=False, error="行数过多", error_code="too_large")
    path = ctx.guard.resolve(args.path, ctx.folders)
    _reject_secret(path, "写入")
    if path.exists() and not ctx.approved:
        raise PermissionError("覆盖文件需要确认")
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "支出"
    sheet.append(list(args.headers))
    for row in args.rows:
        sheet.append(list(row))
    workbook.save(path)
    verified = path.is_file() and path.stat().st_size > 0
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="表格文件已生成且非空",
        message=f"已创建表格 {path}",
        data={"path": str(path), "destination": str(path)},
        error=None if verified else "表格核对失败",
    )


def preflight_rename(args: RenameArgs, ctx: ToolContext) -> Preflight:
    source = ctx.guard.resolve(args.source, ctx.folders)
    destination = source.with_name(_safe_name(args.new_name))
    ctx.guard.resolve(str(destination), ctx.folders)
    return Preflight(
        summary="重命名文件",
        paths=[str(source), str(destination)],
        will_overwrite=destination.exists(),
        impact=f"将 {source} 重命名为 {destination.name}",
    )


def rename_file(args: RenameArgs, ctx: ToolContext) -> ToolResult:
    source = ctx.guard.resolve(args.source, ctx.folders)
    _reject_secret(source, "重命名")
    destination = source.with_name(_safe_name(args.new_name))
    ctx.guard.resolve(str(destination), ctx.folders)
    if not source.exists():
        return ToolResult(ok=False, error="源文件不存在", error_code="not_found")
    if destination.exists() and not ctx.approved:
        raise PermissionError("覆盖文件需要确认")
    size = source.stat().st_size if source.is_file() else None
    shutil.move(str(source), str(destination))
    verified = destination.exists() and not source.exists()
    if verified and size is not None:
        verified = destination.stat().st_size == size
    return ToolResult(
        ok=verified,
        verified=verified,
        verification_detail="源路径已消失，目标路径存在",
        message=f"已重命名为 {destination}",
        data={"source": str(source), "destination": str(destination), "removed_sources": [str(source)]},
        error=None if verified else "重命名后核对失败",
    )


def _destination_for(source: Path, directory: Path) -> Path:
    return directory / source.name


def preflight_transfer(args: TransferArgs, ctx: ToolContext) -> Preflight:
    directory = ctx.guard.resolve(args.destination_directory, ctx.folders)
    paths = []
    overwrite = False
    for raw in args.paths:
        source = ctx.guard.resolve(raw, ctx.folders)
        destination = _destination_for(source, directory)
        paths.extend([str(source), str(destination)])
        overwrite = overwrite or destination.exists()
    return Preflight(
        summary="转移文件",
        paths=paths,
        will_overwrite=overwrite,
        impact=f"将处理 {len(args.paths)} 个文件，目标目录 {directory}",
    )


def _transfer(args: TransferArgs, ctx: ToolContext, move: bool) -> ToolResult:
    if len(args.paths) > MAX_BATCH:
        return ToolResult(ok=False, error="一次处理的文件过多", error_code="too_large")
    directory = ctx.guard.resolve(args.destination_directory, ctx.folders)
    directory.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    removed: list[str] = []
    for raw in args.paths:
        ctx.check_time()
        source = ctx.guard.resolve(raw, ctx.folders)
        _reject_secret(source, "转移")
        if not source.exists():
            return ToolResult(ok=False, error=f"源文件不存在: {source}", error_code="not_found", data={"moved": moved})
        destination = _destination_for(source, directory)
        ctx.guard.resolve(str(destination), ctx.folders)
        if destination.exists() and not ctx.approved:
            raise PermissionError(f"覆盖文件需要确认: {destination}")
        size = source.stat().st_size if source.is_file() else None
        if move:
            shutil.move(str(source), str(destination))
            removed.append(str(source))
        else:
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=bool(ctx.approved))
            else:
                shutil.copy2(source, destination)
        if not destination.exists():
            return ToolResult(ok=False, error=f"目标未出现: {destination}", error_code="verification_failed")
        if size is not None and destination.is_file() and destination.stat().st_size != size:
            return ToolResult(ok=False, error=f"大小不一致: {destination}", error_code="verification_failed")
        moved.append(str(destination))
    action = "移动" if move else "复制"
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail=f"已核对{action}结果",
        message=f"已{action} {len(moved)} 个文件到 {directory}" if moved else "没有文件需要处理",
        data={"destinations": moved, "removed_sources": removed, "count": len(moved), "path": str(directory)},
    )


def move_files(args: TransferArgs, ctx: ToolContext) -> ToolResult:
    return _transfer(args, ctx, move=True)


def copy_files(args: TransferArgs, ctx: ToolContext) -> ToolResult:
    return _transfer(args, ctx, move=False)


def preflight_recycle(args: RecycleArgs, ctx: ToolContext) -> Preflight:
    paths = [str(ctx.guard.resolve(raw, ctx.folders)) for raw in args.paths]
    details = []
    for raw in paths:
        path = Path(raw)
        if path.exists():
            meta = _metadata(path)
            details.append(f"{meta['path']} ({meta['size']} 字节)")
        else:
            details.append(f"{raw} （不存在）")
    return Preflight(
        summary="移动到回收站",
        paths=paths,
        will_overwrite=False,
        impact="这些项目会进入回收站，不会永久删除。\n" + "\n".join(details),
    )


def move_to_recycle_bin(args: RecycleArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("放入回收站必须经过这次操作的确认")
    if len(args.paths) > MAX_BATCH:
        return ToolResult(ok=False, error="一次处理的文件过多", error_code="too_large")
    targets = [ctx.guard.resolve(raw, ctx.folders) for raw in args.paths]
    for path in targets:
        _reject_secret(path, "移入回收站")
        if not path.exists():
            return ToolResult(ok=False, error=f"文件不存在: {path}", error_code="not_found")
    trashed: list[str] = []
    for path in targets:
        ctx.check_time()
        try:
            ctx.platform.send_to_trash(str(path))
        except Exception as exc:
            return ToolResult(
                ok=False,
                error=f"回收站操作失败，已停止，没有永久删除。原因: {exc}",
                error_code="recycle_failed",
                data={"targets": trashed},
            )
        if path.exists():
            return ToolResult(
                ok=False,
                error=f"回收站操作后文件仍在，已停止，没有永久删除: {path}",
                error_code="verification_failed",
                data={"targets": trashed},
            )
        trashed.append(str(path))
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="源路径已消失，且只调用了回收站接口",
        message=f"已将 {len(trashed)} 个项目移到回收站",
        data={"targets": trashed, "count": len(trashed)},
    )


_EXT_GROUPS = {
    "pdf": "PDF",
    "doc": "Documents",
    "docx": "Documents",
    "txt": "Documents",
    "md": "Documents",
    "xls": "Spreadsheets",
    "xlsx": "Spreadsheets",
    "csv": "Spreadsheets",
    "jpg": "Images",
    "jpeg": "Images",
    "png": "Images",
    "gif": "Images",
    "webp": "Images",
    "bmp": "Images",
    "mp4": "Video",
    "mov": "Video",
    "mkv": "Video",
    "mp3": "Audio",
    "wav": "Audio",
    "zip": "Archives",
    "7z": "Archives",
    "rar": "Archives",
}


def preview_organize(args: OrganizeArgs, ctx: ToolContext) -> ToolResult:
    root = ctx.guard.resolve(args.root, ctx.folders)
    if not root.is_dir():
        return ToolResult(ok=False, error="目录不存在", error_code="not_found")
    operations = []
    overwrite = False
    for child in root.iterdir():
        ctx.check_time()
        if not child.is_file() or child.is_symlink() or is_secret_path(child):
            continue
        label = _EXT_GROUPS.get(child.suffix.lower().lstrip("."), "Other")
        destination = root / label / child.name
        if destination.parent == child.parent:
            continue
        overwrite = overwrite or destination.exists()
        operations.append({"src": str(child), "dst": str(destination), "action": "move"})
        if len(operations) >= MAX_BATCH:
            break
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="只生成整理预览，没有移动文件",
        message=f"可整理 {len(operations)} 个文件",
        data={"operations": operations, "count": len(operations), "will_overwrite": overwrite, "root": str(root)},
    )


def preflight_apply(args: ApplyMovesArgs, ctx: ToolContext) -> Preflight:
    paths: list[str] = []
    overwrite = False
    for item in args.operations:
        source = ctx.guard.resolve(str(item.get("src", "")), ctx.folders)
        destination = ctx.guard.resolve(str(item.get("dst", "")), ctx.folders)
        paths.extend([str(source), str(destination)])
        overwrite = overwrite or destination.exists()
    return Preflight(
        summary="按扩展名整理",
        paths=paths,
        will_overwrite=overwrite,
        impact=f"将移动 {len(args.operations)} 个文件。拒绝后不会改动。",
    )


def apply_moves(args: ApplyMovesArgs, ctx: ToolContext) -> ToolResult:
    if args.operations and not ctx.approved:
        raise PermissionError("批量移动必须经过这次预览的确认")
    completed = []
    for item in args.operations:
        ctx.check_time()
        source = ctx.guard.resolve(str(item.get("src", "")), ctx.folders)
        destination = ctx.guard.resolve(str(item.get("dst", "")), ctx.folders)
        _reject_secret(source, "移动")
        if not source.exists():
            return ToolResult(ok=False, error=f"源文件不存在: {source}", error_code="not_found", data={"moved": completed})
        if destination.exists() and not ctx.approved:
            raise PermissionError("覆盖文件需要确认")
        destination.parent.mkdir(parents=True, exist_ok=True)
        size = source.stat().st_size
        shutil.move(str(source), str(destination))
        if source.exists() or not destination.exists() or destination.stat().st_size != size:
            return ToolResult(ok=False, error=f"移动后核对失败: {destination}", error_code="verification_failed")
        completed.append({"src": str(source), "dst": str(destination)})
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="每个目标都已核对大小，源路径已消失",
        message=f"已整理 {len(completed)} 个文件" if completed else "没有需要移动的文件",
        data={"moved": completed, "count": len(completed), "removed_sources": [item["src"] for item in completed]},
    )


def open_file(args: OpenFileArgs, ctx: ToolContext) -> ToolResult:
    path = ctx.guard.resolve(args.path, ctx.folders)
    _reject_secret(path, "打开")
    if not path.is_file():
        return ToolResult(ok=False, error="文件不存在", error_code="not_found")
    ctx.platform.startfile(str(path))
    confirmed = _wait_for_title(ctx, path.stem, timeout=8)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="已调用系统打开，并检查窗口标题" if confirmed else "已调用系统打开，但未在超时内确认窗口",
        message=f"已打开 {path.name}" + ("" if confirmed else "（窗口未确认）"),
        data={"path": str(path), "issued": True, "confirmed": confirmed},
    )


def _wait_for_title(ctx: ToolContext, hint: str, timeout: float) -> bool:
    deadline = time_monotonic_plus(timeout)
    while time_monotonic() < deadline:
        ctx.check_time()
        titles = ctx.platform.window_titles()
        if any(hint.lower() in title.lower() for title in titles):
            return True
        time_sleep(0.15)
    return False


def time_monotonic() -> float:
    import time

    return time.monotonic()


def time_monotonic_plus(seconds: float) -> float:
    return time_monotonic() + seconds


def time_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
