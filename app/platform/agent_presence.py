"""A click-through pointer and banner so the user can see the agent working."""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

POINTER_HOTSPOT = (14, 10)
_BANNER = "Agent is operating"
_CLASS_NAME = "LocalAIAgentPresence"


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32),
        ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


def banner_image(text: str = _BANNER) -> Image.Image:
    image = Image.new("RGBA", (280, 58), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 279, 57), radius=18, fill=(17, 17, 17, 232))
    draw.ellipse((18, 19, 40, 41), fill=(52, 211, 153, 255))
    draw.text((52, 16), text, font=_font(20), fill=(255, 255, 255, 255))
    return image


def pointer_image(pulse: bool = False) -> Image.Image:
    image = Image.new("RGBA", (176, 78), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if pulse:
        draw.ellipse((0, 0, 46, 46), outline=(255, 122, 24, 230), width=4)
    arrow = [(14, 10), (14, 48), (24, 38), (34, 56), (42, 50), (30, 32), (46, 32)]
    draw.polygon(arrow, fill=(255, 122, 24, 255), outline=(255, 255, 255, 255))
    draw.rounded_rectangle((54, 22, 164, 56), radius=12, fill=(17, 17, 17, 235))
    draw.text((70, 28), "Agent", font=_font(20), fill=(255, 255, 255, 255))
    return image


def _font(size: int) -> ImageFont.ImageFont:
    fonts = Path(r"C:\Windows\Fonts")
    for name in ("segoeui.ttf", "arial.ttf"):
        path = fonts / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _wndproc(hwnd, message, wparam, lparam):
    import win32gui

    return win32gui.DefWindowProc(hwnd, message, wparam, lparam)


class AgentPresence:
    """Owns the overlay on one thread so it stays visible while the model thinks."""

    def __init__(self) -> None:
        self.active = False
        self._commands: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._banner = None
        self._pointer = None
        self._pointer_at = (0, 0)
        self._class_ready = False
        self._images: dict[str, Image.Image | None] = {"banner": None, "pointer": None, "pulse": None}

    def begin(self, text: str = _BANNER) -> None:
        self._ensure_thread()
        if self._call("begin", text, timeout=2):
            self.active = True

    def end(self) -> None:
        self.active = False
        if self._thread is None:
            return
        self._call("end", timeout=2)

    def glide(self, x: int, y: int) -> None:
        if not self.active:
            return
        self._call("glide", int(x), int(y), timeout=3)

    def pulse(self) -> None:
        if not self.active:
            return
        self._call("pulse", timeout=1)

    def conceal_pointer(self) -> None:
        if not self.active:
            return
        self._call("conceal", timeout=0.5)

    def reveal_pointer(self) -> None:
        if not self.active:
            return
        self._call("reveal", timeout=0.5)

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="agent-presence", daemon=True)
        self._thread.start()

    def _call(self, *parts: object, timeout: float) -> bool:
        done = threading.Event()
        self._commands.put((*parts, done))
        return done.wait(timeout)

    def _loop(self) -> None:
        while True:
            try:
                command = self._commands.get(timeout=0.05)
            except queue.Empty:
                self._pump()
                continue
            done = command[-1]
            try:
                self._dispatch(command[:-1])
            except Exception:
                log.exception("agent presence")
            finally:
                if isinstance(done, threading.Event):
                    done.set()

    def _dispatch(self, command: tuple) -> None:
        kind = command[0]
        if kind == "begin":
            self._show(str(command[1]))
        elif kind == "end":
            self._hide()
        elif kind == "glide":
            self._glide(int(command[1]), int(command[2]))
        elif kind == "pulse":
            self._pulse()
        elif kind == "conceal":
            self._show_pointer(False)
        elif kind == "reveal":
            self._show_pointer(True)

    def _show(self, text: str) -> None:
        import win32gui

        self._images["banner"] = banner_image(text)
        self._images["pointer"] = pointer_image(False)
        self._images["pulse"] = pointer_image(True)
        if self._banner is None:
            self._banner = self._create_window()
            self._pointer = self._create_window()
        bounds = _virtual_screen()
        banner = self._images["banner"]
        assert banner is not None
        left = int(bounds["left"] + (bounds["width"] - banner.width) / 2)
        top = int(bounds["top"] + 28)
        self._paint(self._banner, banner, left, top)
        point = _pointer_pos()
        self._pointer_at = point
        self._place_pointer(point[0], point[1], pulse=False)
        win32gui.ShowWindow(self._banner, 4)
        win32gui.ShowWindow(self._pointer, 4)
        self._pump()

    def _hide(self) -> None:
        import win32gui

        for hwnd in (self._pointer, self._banner):
            if hwnd:
                win32gui.ShowWindow(hwnd, 0)
        self._pump()

    def _glide(self, x: int, y: int) -> None:
        start = _pointer_pos()
        steps = 28
        for index in range(1, steps + 1):
            eased = 1 - (1 - index / steps) ** 3
            nx = int(start[0] + (x - start[0]) * eased)
            ny = int(start[1] + (y - start[1]) * eased)
            _move_pointer(nx, ny)
            self._place_pointer(nx, ny, pulse=False)
            self._pump()
            time.sleep(0.025)
        _move_pointer(x, y)
        self._place_pointer(x, y, pulse=False)

    def _pulse(self) -> None:
        x, y = self._pointer_at
        self._place_pointer(x, y, pulse=True)
        time.sleep(0.16)
        self._place_pointer(x, y, pulse=False)

    def _show_pointer(self, visible: bool) -> None:
        import win32gui

        if self._pointer:
            win32gui.ShowWindow(self._pointer, 4 if visible else 0)

    def _place_pointer(self, x: int, y: int, pulse: bool) -> None:
        if not self._pointer:
            return
        image = self._images["pulse" if pulse else "pointer"]
        if image is None:
            return
        self._pointer_at = (x, y)
        self._paint(self._pointer, image, x - POINTER_HOTSPOT[0], y - POINTER_HOTSPOT[1])

    def _create_window(self) -> int:
        import win32api
        import win32gui

        instance = win32api.GetModuleHandle(None)
        if not self._class_ready:
            window_class = win32gui.WNDCLASS()
            window_class.hInstance = instance
            window_class.lpszClassName = _CLASS_NAME
            window_class.lpfnWndProc = _wndproc
            try:
                win32gui.RegisterClass(window_class)
            except win32gui.error:
                pass
            self._class_ready = True
        extended = 0x80000 | 0x20 | 0x8 | 0x80 | 0x08000000
        return win32gui.CreateWindowEx(extended, _CLASS_NAME, "", 0x80000000, 0, 0, 10, 10, 0, 0, instance, None)

    def _paint(self, hwnd: int, image: Image.Image, x: int, y: int) -> None:
        import win32gui

        width, height = image.size
        raw = bytearray(image.tobytes("raw", "BGRA"))
        for offset in range(0, len(raw), 4):
            alpha = raw[offset + 3]
            raw[offset] = raw[offset] * alpha // 255
            raw[offset + 1] = raw[offset + 1] * alpha // 255
            raw[offset + 2] = raw[offset + 2] * alpha // 255
        header = _BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        _bind_layered(user32, gdi32)
        screen = user32.GetDC(0)
        memory = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(memory, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if bitmap and bits:
            ctypes.memmove(bits, bytes(raw), len(raw))
        previous = gdi32.SelectObject(memory, bitmap)
        origin = wintypes.POINT(int(x), int(y))
        size = _SIZE(width, height)
        source = wintypes.POINT(0, 0)
        blend = _BLENDFUNCTION(0, 0, 255, 1)
        painted = user32.UpdateLayeredWindow(
            hwnd,
            screen,
            ctypes.byref(origin),
            ctypes.byref(size),
            memory,
            ctypes.byref(source),
            0,
            ctypes.byref(blend),
            2,
        )
        if not painted and not getattr(_bind_layered, "reported", False):
            _bind_layered.reported = True
            log.warning("agent overlay was not painted: %s", ctypes.get_last_error())
        gdi32.SelectObject(memory, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(0, screen)
        win32gui.SetWindowPos(hwnd, -1, int(x), int(y), width, height, 0x0010 | 0x0040)

    def _pump(self) -> None:
        user32 = ctypes.windll.user32
        message = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(message), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))


def _bind_layered(user32, gdi32) -> None:
    if getattr(_bind_layered, "ready", False):
        return
    user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND,
        wintypes.HDC,
        ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(_SIZE),
        wintypes.HDC,
        ctypes.POINTER(wintypes.POINT),
        wintypes.DWORD,
        ctypes.POINTER(_BLENDFUNCTION),
        wintypes.DWORD,
    ]
    user32.UpdateLayeredWindow.restype = wintypes.BOOL
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BITMAPINFOHEADER),
        ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        ctypes.c_uint32,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HGDIOBJ
    _bind_layered.ready = True


def _pointer_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _move_pointer(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _virtual_screen() -> dict[str, int]:
    from app.platform.winlib import virtual_screen

    return virtual_screen()


presence = AgentPresence()
