"""In-memory Windows stand-in. Tests never touch the real desktop."""

from __future__ import annotations

import shutil
from pathlib import Path


class FakePlatform:
    def __init__(self) -> None:
        self.trashed: list[str] = []
        self.opened: list[str] = []
        self.wallpapers: list[str] = []
        self.launched: list[tuple[str, list[str]]] = []
        self.clicks: list[tuple] = []
        self.typed: list[tuple] = []
        self.presence = False
        self.presence_log: list[tuple[bool, str]] = []
        self.titles = ["Test window"]
        self.foreground = "Test window"
        self.appearance = "light"
        self.fail_trash = False
        self._wallpaper = ""
        self.controls = [
            {
                "name": "Sign in",
                "control_type": "Hyperlink",
                "is_password": False,
                "rect": (400, 120, 480, 160),
                "window": "YouTube - Google Chrome",
            }
        ]

    def send_to_trash(self, path: str) -> None:
        if self.fail_trash:
            raise RuntimeError("recycle unavailable")
        source = Path(path)
        destination = source.parent / "_trash" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        self.trashed.append(path)

    def startfile(self, path: str) -> None:
        self.opened.append(path)
        self.titles.append(Path(path).stem)

    def open_url(self, url: str) -> None:
        self.opened.append(url)

    def open_browser(self, url: str) -> str:
        self.opened.append(url)
        self.titles.append("YouTube - Google Chrome" if "youtube.com" in url else "Browser")
        return "chrome.exe"

    def click_named(self, name: str, window_title: str, cancel_event, deadline: float, pick: str = "") -> dict:
        del cancel_event, deadline
        if pick == "first_video":
            self.click(640, 420)
            return {"ok": True, "x": 640, "y": 420, "name": "first video", "error": None, "error_code": None}
        alternatives = [part.strip().lower() for part in name.split("|") if part.strip()]
        for control in self.controls:
            if control.get("is_password"):
                continue
            if window_title and window_title.lower() not in str(control.get("window", "")).lower():
                continue
            control_name = str(control.get("name", ""))
            lowered = control_name.lower()
            if not any(item in lowered or lowered in item for item in alternatives):
                continue
            left, top, right, bottom = control["rect"]
            x, y = (left + right) // 2, (top + bottom) // 2
            self.click(x, y)
            return {"ok": True, "x": x, "y": y, "name": control_name, "error": None, "error_code": None}
        return {
            "ok": False,
            "x": None,
            "y": None,
            "name": "",
            "error": "No clickable control was found in the window",
            "error_code": "window_not_ready",
        }

    def list_window_controls(self, title_part: str) -> list[dict]:
        rows: list[dict] = []
        for control in self.controls:
            if title_part.lower() not in str(control.get("window", "")).lower():
                continue
            left, top, right, bottom = control["rect"]
            rows.append(
                {
                    "name": str(control.get("name", "")),
                    "control_type": str(control.get("control_type", "")),
                    "value": str(control.get("value") or ""),
                    "left": int(left),
                    "top": int(top),
                    "right": int(right),
                    "bottom": int(bottom),
                }
            )
        return rows

    def find_window(self, title_part: str) -> dict | None:
        for title in self.titles:
            if title_part.lower() in title.lower():
                return {"title": title, "left": 0, "top": 0, "right": 1280, "bottom": 720}
        return None

    def window_titles(self) -> list[str]:
        return list(self.titles)

    def foreground_title(self) -> str:
        return self.foreground

    def focus_window(self, title: str) -> bool:
        for item in self.titles:
            if title.lower() in item.lower():
                self.foreground = item
                return True
        return False

    def close_window(self, title: str) -> bool:
        remaining = [item for item in self.titles if title.lower() not in item.lower()]
        if len(remaining) == len(self.titles):
            return False
        self.titles = remaining
        return True

    def launch(self, executable: str, args: list[str]) -> int:
        self.launched.append((executable, list(args)))
        self.titles.append(Path(args[-1]).name if args else Path(executable).stem)
        return 123

    def process_exists(self, name: str) -> bool:
        return any(executable.lower() == name.lower() for executable, _args in self.launched)

    def virtual_screen(self) -> dict[str, int]:
        return {"left": 0, "top": 0, "width": 1920, "height": 1080}

    def set_agent_presence(self, active: bool, text: str = "") -> None:
        self.presence = active
        self.presence_log.append((active, text))

    def glide_to(self, x: int, y: int) -> None:
        self.clicks.append(("glide", x, y))

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        self.clicks.append((x, y, button, clicks))

    def move_mouse(self, x: int, y: int) -> None:
        self.clicks.append(("move", x, y))

    def scroll(self, amount: int) -> None:
        self.clicks.append(("scroll", amount))

    def drag_drop(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self.clicks.append(("drag", start, end))

    def type_text(self, text: str) -> None:
        self.typed.append(("text", text))

    def hotkey(self, keys: list[str]) -> None:
        self.typed.append(("hotkey", tuple(keys)))

    def press_key(self, key: str) -> None:
        self.typed.append(("key", key))

    def mouse_position(self) -> tuple[int, int]:
        return 20, 20

    def capture(self, target: str, monitor_index: int, destination: Path) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fakepng")
        return str(destination)

    def ui_tree(self) -> dict:
        return {
            "available": True,
            "dialogs": [],
            "elements": [
                {"name": "Save", "control_type": "Button", "automation_id": "save", "is_password": False},
                {"name": "super-secret", "control_type": "Edit", "automation_id": "password", "is_password": True},
            ],
        }

    def set_wallpaper(self, path: str) -> str:
        self.wallpapers.append(path)
        self._wallpaper = path
        return path

    def get_wallpaper(self) -> str:
        return self._wallpaper

    def get_appearance(self) -> str:
        return self.appearance

    def set_appearance(self, mode: str) -> str:
        if mode not in {"light", "dark"}:
            raise ValueError(mode)
        self.appearance = mode
        return mode

    def open_settings(self, uri: str) -> None:
        self.opened.append(uri)
        self.titles.append("Settings")

    def read_page_title(self, url: str, _cancel_event) -> str:
        self.opened.append(url)
        return "Example Domain"
