"""Windows known folders and small native helpers."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


_KNOWN = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1C-4673-AEFE-87A97D0D6E5F",
}


def _guid(text: str) -> GUID:
    compact = text.replace("{", "").replace("}", "").replace("-", "")
    data4 = bytes.fromhex(compact[16:32])
    value = GUID()
    value.Data1 = int(compact[0:8], 16)
    value.Data2 = int(compact[8:12], 16)
    value.Data3 = int(compact[12:16], 16)
    for index, byte in enumerate(data4):
        value.Data4[index] = byte
    return value


def known_folder(name: str) -> Path | None:
    guid_text = _KNOWN.get(name)
    if guid_text is None:
        return None
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        pointer = ctypes.c_wchar_p()
        result = shell32.SHGetKnownFolderPath(ctypes.byref(_guid(guid_text)), 0, None, ctypes.byref(pointer))
        if result != 0 or not pointer.value:
            return None
        try:
            path = Path(pointer.value)
        finally:
            ole32.CoTaskMemFree(pointer)
        return path if path.exists() else None
    except Exception:
        return None


def fallback_folder(name: str) -> Path:
    home = Path.home()
    mapping = {
        "desktop": home / "Desktop",
        "documents": home / "Documents",
        "downloads": home / "Downloads",
        "pictures": home / "Pictures",
    }
    return mapping[name]


def discover_known_folders() -> dict[str, Path]:
    folders: dict[str, Path] = {}
    for name in ("downloads", "documents", "desktop", "pictures"):
        path = known_folder(name) or fallback_folder(name)
        if path.exists():
            folders[name] = path
    return folders


def virtual_screen() -> dict[str, int]:
    user32 = ctypes.windll.user32
    return {
        "left": int(user32.GetSystemMetrics(76)),
        "top": int(user32.GetSystemMetrics(77)),
        "width": int(user32.GetSystemMetrics(78)),
        "height": int(user32.GetSystemMetrics(79)),
    }


def point_inside(x: int, y: int, bounds: dict[str, int]) -> bool:
    return (
        bounds["left"] <= x < bounds["left"] + bounds["width"]
        and bounds["top"] <= y < bounds["top"] + bounds["height"]
    )
