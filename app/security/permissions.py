"""Filesystem scope, protected paths, and sensitive-file checks."""

from __future__ import annotations

import os
from pathlib import Path

DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *{f"com{index}" for index in range(1, 10)},
    *{f"lpt{index}" for index in range(1, 10)},
}

LOGICAL_ALIASES = {
    "download": "downloads",
    "downloads": "downloads",
    "document": "documents",
    "documents": "documents",
    "desktop": "desktop",
    "picture": "pictures",
    "pictures": "pictures",
    "photo": "pictures",
    "photos": "pictures",
    "下载": "downloads",
    "文档": "documents",
    "桌面": "desktop",
    "图片": "pictures",
}

SECRET_FILENAMES = {
    ".env",
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}


def default_protected_prefixes() -> list[Path]:
    values = [
        os.environ.get("WINDIR", r"C:\Windows"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramData", r"C:\ProgramData"),
        str(Path.home() / "AppData"),
    ]
    prefixes: list[Path] = []
    for raw in values:
        if not raw:
            continue
        path = Path(raw)
        if path not in prefixes:
            prefixes.append(path)
    return prefixes


def is_drive_root(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    return resolved == Path(resolved.anchor)


def is_secret_path(path: str | Path) -> bool:
    name = Path(path).name.lower()
    if name in SECRET_FILENAMES or name.endswith((".pem", ".key", ".pfx", ".kdbx")):
        return True
    return "password" in name or "secret" in name or name.startswith(".env")


class PathGuard:
    """Allow mutation and search only inside configured roots, never inside protected prefixes."""

    def __init__(self, allowed_roots: list[Path], protected_prefixes: list[Path] | None = None) -> None:
        self.allowed_roots = [self._absolute(path) for path in allowed_roots]
        incoming = default_protected_prefixes() if protected_prefixes is None else protected_prefixes
        self.protected_prefixes = self._filter_protected(incoming)

    def _filter_protected(self, protected: list[Path]) -> list[Path]:
        """Keep system directories protected even when a sandbox root sits inside AppData."""
        hard_names = {"windows", "program files", "program files (x86)", "programdata"}
        kept: list[Path] = []
        for prefix in protected:
            absolute = self._absolute(prefix)
            if absolute.name.lower() in hard_names:
                kept.append(absolute)
                continue
            if any(self._contains(absolute, root) for root in self.allowed_roots):
                continue
            kept.append(absolute)
        return kept

    @staticmethod
    def _contains(parent: Path, child: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _absolute(path: Path) -> Path:
        return Path(os.path.abspath(path))

    def resolve(self, raw: str, folders: dict[str, Path] | None = None) -> Path:
        if raw is None or not str(raw).strip():
            raise PermissionError("路径为空")
        text = str(raw).strip().strip('"').strip("'")
        self._reject_special(text)
        logical = self._from_logical(text, folders or {})
        candidate = logical if logical is not None else Path(text)
        if logical is None and not candidate.is_absolute():
            raise PermissionError("相对路径不被允许，请使用文档、下载、桌面、图片或绝对路径")
        resolved = self._harden(candidate)
        self._ensure(resolved)
        leaf = resolved.name.split(".")[0].lower()
        if leaf in DEVICE_NAMES:
            raise PermissionError("路径使用了保留设备名")
        return resolved

    def _reject_special(self, text: str) -> None:
        normalized = text.replace("/", "\\")
        if normalized.startswith("\\\\"):
            raise PermissionError("不允许网络路径或设备路径")
        rest = normalized[2:] if len(normalized) > 2 and normalized[1] == ":" else normalized
        if ":" in rest:
            raise PermissionError("不允许备用数据流")

    def _from_logical(self, text: str, folders: dict[str, Path]) -> Path | None:
        parts = [part for part in text.replace("\\", "/").split("/") if part]
        if not parts:
            return None
        key = LOGICAL_ALIASES.get(parts[0].lower(), parts[0].lower())
        if key not in folders and parts[0] not in folders:
            return None
        base = folders.get(key) or folders[parts[0]]
        extra = parts[1:]
        if any(part in {".", ".."} for part in extra):
            raise PermissionError("路径不能包含上级目录跳转")
        return Path(base).joinpath(*extra)

    def _harden(self, candidate: Path) -> Path:
        absolute = Path(os.path.abspath(candidate))
        if absolute.exists():
            return Path(os.path.realpath(absolute))
        missing: list[str] = []
        current = absolute
        while not current.exists() and current.parent != current:
            missing.append(current.name)
            current = current.parent
        if not current.exists():
            return absolute
        base = Path(os.path.realpath(current))
        for name in reversed(missing):
            if name in {".", ".."}:
                raise PermissionError("非法路径")
            base = base / name
        return base

    def _ensure(self, resolved: Path) -> None:
        if self._under_any(resolved, self.protected_prefixes):
            raise PermissionError(f"路径受保护，已拒绝: {resolved}")
        if not self._under_any(resolved, self.allowed_roots):
            raise PermissionError(f"路径超出允许范围，已拒绝: {resolved}")

    @staticmethod
    def _under_any(path: Path, roots: list[Path]) -> bool:
        for root in roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False
