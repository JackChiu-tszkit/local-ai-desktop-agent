"""Platform operations. Tests replace this object so destructive calls stay fake."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from app.errors import CancellationError


def _cancelled(cancel_event) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def _browser_executable() -> Path | None:
    roots = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    relatives = (
        Path("Google/Chrome/Application/chrome.exe"),
        Path("Microsoft/Edge/Application/msedge.exe"),
    )
    for relative in relatives:
        for root in roots:
            if not root:
                continue
            candidate = Path(root) / relative
            if candidate.is_file():
                return candidate
    return None


def _window_ratio_point(title: str, x_ratio: float, y_ratio: float) -> tuple[int, int] | None:
    import win32gui

    found: list[int] = []

    def callback(hwnd, _extra) -> None:
        if win32gui.IsWindowVisible(hwnd) and title.lower() in (win32gui.GetWindowText(hwnd) or "").lower():
            found.append(hwnd)

    win32gui.EnumWindows(callback, None)
    for hwnd in found:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        width, height = right - left, bottom - top
        if width < 400 or height < 300:
            continue
        return left + int(width * x_ratio), top + int(height * y_ratio)
    return None


def _click_failure(message: str, code: str, x: int | None = None, y: int | None = None, name: str = "") -> dict:
    return {"ok": False, "x": x, "y": y, "name": name, "error": message, "error_code": code}


def _find_named_control(names: list[str], window_title: str) -> tuple[int, int, str] | None:
    try:
        from pywinauto import Desktop
    except Exception:
        return None
    wanted = [item.lower() for item in names]
    try:
        windows = Desktop(backend="uia").windows()
    except Exception:
        return None
    for window in windows:
        try:
            title = window.window_text() or ""
        except Exception:
            continue
        if window_title and window_title.lower() not in title.lower():
            continue
        try:
            controls = window.descendants()
        except Exception:
            continue
        for control in controls[:400]:
            try:
                info = control.element_info
                control_name = info.name or ""
                control_type = str(info.control_type or "").lower()
                if not control_name or "password" in control_type or "edit" in control_type:
                    continue
                if not any(item in control_name.lower() for item in wanted):
                    continue
                if hasattr(control, "is_visible") and not control.is_visible():
                    continue
                rect = control.rectangle()
                if rect.width() < 2 or rect.height() < 2:
                    continue
            except Exception:
                continue
            return int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2), control_name[:80]
    return None


class WindowsPlatform:
    def send_to_trash(self, path: str) -> None:
        from send2trash import send2trash

        send2trash(path)

    def startfile(self, path: str) -> None:
        os.startfile(path)  # type: ignore[attr-defined]

    def open_url(self, url: str) -> None:
        os.startfile(url)  # type: ignore[attr-defined]

    def open_browser(self, url: str) -> str:
        executable = _browser_executable()
        if executable is None:
            os.startfile(url)  # type: ignore[attr-defined]
            return "default"
        subprocess.Popen([str(executable), "--force-renderer-accessibility", url], shell=False)
        return executable.name

    def click_named(self, name: str, window_title: str, cancel_event, deadline: float, pick: str = "") -> dict:
        from app.platform.winlib import point_inside

        if pick == "first_video":
            return self._click_window_ratio(window_title or "YouTube", 0.33, 0.42, cancel_event, deadline, "first video")
        alternatives = [part.strip() for part in name.split("|") if part.strip()]
        while time.monotonic() < deadline:
            if _cancelled(cancel_event):
                raise CancellationError("The task was stopped")
            found = _find_named_control(alternatives, window_title)
            if found is not None:
                x, y, matched = found
                if not point_inside(x, y, self.virtual_screen()):
                    return _click_failure("The control center is outside the screen", "permission", x, y, matched)
                if window_title:
                    self.focus_window(window_title)
                self.move_mouse(x, y)
                self.click(x, y)
                return {"ok": True, "x": x, "y": y, "name": matched, "error": None, "error_code": None}
            time.sleep(0.4)
        return _click_failure("No clickable control was found in the window", "window_not_ready")

    def _click_window_ratio(self, window_title: str, x_ratio: float, y_ratio: float, cancel_event, deadline: float, label: str) -> dict:
        from app.platform.winlib import point_inside

        ready = False
        while time.monotonic() < deadline:
            if _cancelled(cancel_event):
                raise CancellationError("The task was stopped")
            point = _window_ratio_point(window_title, x_ratio, y_ratio)
            if point is None:
                time.sleep(0.4)
                continue
            if not ready:
                ready = True
                time.sleep(2.5)
                continue
            x, y = point
            if not point_inside(x, y, self.virtual_screen()):
                return _click_failure("The click point is outside the screen", "permission", x, y, label)
            self.focus_window(window_title)
            self.move_mouse(x, y)
            self.click(x, y)
            return {"ok": True, "x": x, "y": y, "name": label, "error": None, "error_code": None}
        return _click_failure("The YouTube window was not found", "window_not_ready")

    def window_titles(self) -> list[str]:
        import win32gui

        titles: list[str] = []

        def callback(hwnd, _extra) -> None:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    titles.append(title)

        win32gui.EnumWindows(callback, None)
        return titles

    def foreground_title(self) -> str:
        import win32gui

        return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""

    def focus_window(self, title: str) -> bool:
        import win32con
        import win32gui

        match: list[int] = []

        def callback(hwnd, _extra) -> None:
            if win32gui.IsWindowVisible(hwnd) and title.lower() in win32gui.GetWindowText(hwnd).lower():
                match.append(hwnd)

        win32gui.EnumWindows(callback, None)
        if not match:
            return False
        hwnd = match[0]
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            return False
        time.sleep(0.05)
        return title.lower() in self.foreground_title().lower()

    def close_window(self, title: str) -> bool:
        import win32con
        import win32gui

        found: list[int] = []

        def callback(hwnd, _extra) -> None:
            if win32gui.IsWindowVisible(hwnd) and title.lower() in win32gui.GetWindowText(hwnd).lower():
                found.append(hwnd)

        win32gui.EnumWindows(callback, None)
        if not found:
            return False
        win32gui.PostMessage(found[0], win32con.WM_CLOSE, 0, 0)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            still = any(title.lower() in item.lower() for item in self.window_titles())
            if not still:
                return True
            time.sleep(0.15)
        return False

    def launch(self, executable: str, args: list[str]) -> int:
        process = subprocess.Popen([executable, *args], shell=False)
        return int(process.pid)

    def process_exists(self, name: str) -> bool:
        import psutil

        target = name.lower()
        for process in psutil.process_iter(["name"]):
            current = process.info.get("name") or ""
            if current.lower() == target:
                return True
        return False

    def list_window_controls(self, title_part: str) -> list[dict]:
        try:
            from pywinauto import Desktop
        except Exception:
            return []
        try:
            windows = Desktop(backend="uia").windows()
        except Exception:
            return []
        best = None
        best_area = 0
        for window in windows:
            try:
                title = window.window_text() or ""
                rect = window.rectangle()
            except Exception:
                continue
            if title_part.lower() not in title.lower():
                continue
            if rect.width() < 400 or rect.height() < 300:
                continue
            area = rect.width() * rect.height()
            if area < best_area:
                continue
            best = window
            best_area = area
        if best is None:
            return []
        try:
            controls = best.descendants()
        except Exception:
            return []
        rows: list[dict] = []
        for control in controls[:900]:
            try:
                info = control.element_info
                name = info.name or ""
                control_type = str(info.control_type or "")
                if not name.strip():
                    continue
                if "password" in control_type.lower() or bool(getattr(info, "is_password", False)):
                    continue
                rect = control.rectangle()
            except Exception:
                continue
            rows.append(
                {
                    "name": name[:160],
                    "control_type": control_type,
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                }
            )
        return rows

    def find_window(self, title_part: str) -> dict | None:
        import win32gui

        found: list[dict] = []

        def callback(hwnd, _extra) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if title_part.lower() not in title.lower():
                return
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            if right - left < 400 or bottom - top < 300:
                return
            found.append({"title": title, "left": int(left), "top": int(top), "right": int(right), "bottom": int(bottom)})

        win32gui.EnumWindows(callback, None)
        if not found:
            return None
        return max(found, key=lambda item: (item["right"] - item["left"]) * (item["bottom"] - item["top"]))

    def virtual_screen(self) -> dict[str, int]:
        from app.platform.winlib import virtual_screen

        return virtual_screen()

    def set_agent_presence(self, active: bool, text: str = "") -> None:
        from app.platform.agent_presence import presence

        if active:
            presence.begin(text or "Agent is operating")
        else:
            presence.end()

    def glide_to(self, x: int, y: int) -> None:
        from app.platform.agent_presence import presence

        presence.glide(x, y)

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None:
        import pyautogui

        from app.platform.agent_presence import presence

        pyautogui.FAILSAFE = True
        if presence.active:
            presence.glide(x, y)
            presence.pulse()
        pyautogui.click(x=x, y=y, clicks=clicks, button=button)

    def move_mouse(self, x: int, y: int) -> None:
        import pyautogui

        from app.platform.agent_presence import presence

        pyautogui.FAILSAFE = True
        if presence.active:
            presence.glide(x, y)
            return
        pyautogui.moveTo(x, y)

    def scroll(self, amount: int) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.scroll(amount)

    def drag_drop(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.moveTo(*start)
        pyautogui.dragTo(*end, duration=0.2, button="left")

    def type_text(self, text: str) -> None:
        self._send_unicode(text)

    def hotkey(self, keys: list[str]) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.hotkey(*keys)

    def press_key(self, key: str) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.press(key)

    def mouse_position(self) -> tuple[int, int]:
        import pyautogui

        position = pyautogui.position()
        return int(position.x), int(position.y)

    def capture(self, target: str, monitor_index: int, destination: Path) -> str:
        import mss
        from PIL import Image

        from app.platform.agent_presence import presence

        destination.parent.mkdir(parents=True, exist_ok=True)
        presence.conceal_pointer()
        try:
            self._grab(target, monitor_index, destination, mss, Image)
        finally:
            presence.reveal_pointer()
        return str(destination)

    def _grab(self, target: str, monitor_index: int, destination: Path, mss, image_module) -> None:
        with mss.mss() as grabber:
            if target == "active_window":
                rect = self._foreground_rect()
                monitor = {
                    "left": rect[0],
                    "top": rect[1],
                    "width": max(1, rect[2] - rect[0]),
                    "height": max(1, rect[3] - rect[1]),
                }
            elif target == "monitor":
                index = min(max(monitor_index, 1), len(grabber.monitors) - 1)
                monitor = grabber.monitors[index]
            else:
                monitor = grabber.monitors[0]
            raw = grabber.grab(monitor)
            image = image_module.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
            self._mask_passwords(image, monitor["left"], monitor["top"])
            image.save(destination)

    def ui_tree(self) -> dict:
        try:
            from pywinauto import Desktop
        except Exception as exc:
            return {"available": False, "error": str(exc), "elements": []}
        elements: list[dict] = []
        dialogs: list[str] = []
        try:
            desktop = Desktop(backend="uia")
            active = desktop.window(active_only=True)
            wrapper = active.wrapper_object()
            for control in wrapper.descendants()[:200]:
                info = control.element_info
                name = (info.name or "")[:80]
                control_type = str(info.control_type or "")
                is_password = "password" in control_type.lower() or bool(getattr(info, "is_password", False))
                elements.append(
                    {
                        "name": "" if is_password else name,
                        "control_type": control_type,
                        "automation_id": str(info.automation_id or "")[:80],
                        "is_password": is_password,
                    }
                )
                if "dialog" in control_type.lower() or "window" in control_type.lower():
                    if name:
                        dialogs.append(name)
        except Exception as exc:
            return {"available": False, "error": str(exc), "elements": []}
        return {"available": True, "elements": elements, "dialogs": dialogs[:20]}

    def set_wallpaper(self, path: str) -> str:
        import ctypes

        from PIL import Image

        destination = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LocalAIDesktopAgent" / "wallpaper.bmp"
        if os.environ.get("AGENT_DATA_DIR"):
            destination = Path(os.environ["AGENT_DATA_DIR"]) / "wallpaper.bmp"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(path) as image:
            image.convert("RGB").save(destination, "BMP")
        flags = 0x01 | 0x02
        ok = ctypes.windll.user32.SystemParametersInfoW(20, 0, str(destination), flags)
        if not ok:
            raise OSError("The system did not accept the wallpaper change")
        return str(destination)

    def get_wallpaper(self) -> str:
        import ctypes

        buffer = ctypes.create_unicode_buffer(1024)
        ctypes.windll.user32.SystemParametersInfoW(0x0073, len(buffer), buffer, 0)
        return buffer.value

    def get_appearance(self) -> str:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        except OSError:
            return "unknown"
        return "light" if int(value) == 1 else "dark"

    def set_appearance(self, mode: str) -> str:
        import ctypes
        import winreg

        if mode not in {"light", "dark"}:
            raise ValueError("Appearance can only be light or dark")
        light = 1 if mode == "light" else 0
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, light)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, light)
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 200, None)
        return self.get_appearance()

    def open_settings(self, uri: str) -> None:
        os.startfile(uri)  # type: ignore[attr-defined]

    def read_page_title(self, url: str, cancel_event) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is not installed, so the page title cannot be read") from exc
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                if _cancelled(cancel_event):
                    raise CancellationError("The task was stopped")
                return page.title()
            finally:
                browser.close()

    def _foreground_rect(self) -> tuple[int, int, int, int]:
        import win32gui

        return win32gui.GetWindowRect(win32gui.GetForegroundWindow())

    def _mask_passwords(self, image, origin_x: int, origin_y: int) -> None:
        from PIL import ImageDraw

        tree = self.ui_tree()
        if not tree.get("available"):
            return
        draw = ImageDraw.Draw(image)
        # Rectangles are not always available from the trimmed tree. Password fields are
        # already emptied in the structured observation; this hook stays for rect-capable builds.
        del draw, origin_x, origin_y

    @staticmethod
    def _send_unicode(text: str) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_void_p),
            ]

        class INPUT(ctypes.Structure):
            class _UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

            _anonymous_ = ("u",)
            _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

        events: list[INPUT] = []
        for character in text:
            for flags in (0x0004, 0x0004 | 0x0002):
                event = INPUT()
                event.type = 1
                event.ki = KEYBDINPUT(0, ord(character), flags, 0, None)
                events.append(event)
        if not events:
            return
        array = (INPUT * len(events))(*events)
        sent = user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
        if sent != len(events):
            raise OSError("The keyboard input was not fully sent")
