"""Windows mouse and keyboard backend using native Win32 SendInput via ctypes."""

import ctypes
import sys
import threading
from collections.abc import Sequence
from ctypes import wintypes

from aileron.interfaces import (
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    Intent,
    Key,
    MoveBy,
    MoveTo,
    ReleaseAll,
    Scroll,
    Zoom,
)

# Win32 SendInput constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000

KEYEVENTF_KEYUP = 0x0002
WHEEL_DELTA = 120
SCROLL_EPSILON = 1e-4

VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt
VK_ESCAPE = 0x1B

ULONG_PTR = wintypes.WPARAM


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTUNION),
    ]


class WindowsMouseKeyboardBackend:
    """Windows native mouse and keyboard input injector using SendInput.

    Safe by design: accepts an optional user32 mock for headless verification.
    """

    name: str = "windows_mouse_keyboard"
    capabilities: frozenset[str] = frozenset({"mouse", "keyboard"})

    def __init__(self, user32_mock: object | None = None) -> None:
        self._lock = threading.RLock()
        self._is_open = False
        self._held_items: set[str] = set()

        if user32_mock is not None:
            self._user32 = user32_mock
        elif sys.platform == "win32":
            self._user32 = ctypes.windll.user32
        else:
            self._user32 = None

    def open(self) -> None:
        with self._lock:
            self._is_open = True

    def close(self) -> None:
        self.release_all()
        with self._lock:
            self._is_open = False

    def held(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._held_items)

    def _send_mouse_input(
        self,
        flags: int,
        dx: int = 0,
        dy: int = 0,
        data: int = 0,
    ) -> None:
        if self._user32 is None:
            return
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = dx
        inp.union.mi.dy = dy
        inp.union.mi.mouseData = data
        inp.union.mi.dwFlags = flags
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = 0
        send_fn = getattr(self._user32, "SendInput", None)
        if callable(send_fn):
            send_fn(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _send_key_input(self, vk: int, is_up: bool = False) -> None:
        if self._user32 is None:
            return
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.wScan = 0
        inp.union.ki.dwFlags = KEYEVENTF_KEYUP if is_up else 0
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = 0
        send_fn = getattr(self._user32, "SendInput", None)
        if callable(send_fn):
            send_fn(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def release_all(self) -> None:
        """Immediately release all held buttons and keys without raising."""
        with self._lock:
            if "button:left" in self._held_items:
                self._send_mouse_input(MOUSEEVENTF_LEFTUP)
            if "button:right" in self._held_items:
                self._send_mouse_input(MOUSEEVENTF_RIGHTUP)
            if "button:middle" in self._held_items:
                self._send_mouse_input(MOUSEEVENTF_MIDDLEUP)
            if "key:ctrl" in self._held_items:
                self._send_key_input(VK_CONTROL, is_up=True)
            self._held_items.clear()

    def _handle_button(self, btn: Button, down: bool) -> None:
        btn_map = {
            Button.LEFT: (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, "button:left"),
            Button.RIGHT: (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, "button:right"),
            Button.MIDDLE: (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, "button:middle"),
        }
        flag_down, flag_up, tag = btn_map[btn]
        if down:
            self._send_mouse_input(flag_down)
            self._held_items.add(tag)
        else:
            self._send_mouse_input(flag_up)
            self._held_items.discard(tag)

    def _handle_scroll_or_zoom(self, intent: Intent) -> None:
        if isinstance(intent, Scroll):
            if abs(intent.dy) > SCROLL_EPSILON:
                delta = round(intent.dy * WHEEL_DELTA)
                self._send_mouse_input(MOUSEEVENTF_WHEEL, data=delta)
            if abs(intent.dx) > SCROLL_EPSILON:
                delta = round(intent.dx * WHEEL_DELTA)
                self._send_mouse_input(MOUSEEVENTF_HWHEEL, data=delta)
        elif isinstance(intent, Zoom):
            self._send_key_input(VK_CONTROL, is_up=False)
            delta = round(intent.steps * WHEEL_DELTA)
            self._send_mouse_input(MOUSEEVENTF_WHEEL, data=delta)
            self._send_key_input(VK_CONTROL, is_up=True)

    def _apply_one(self, intent: Intent) -> None:
        if isinstance(intent, MoveTo):
            set_cursor = getattr(self._user32, "SetCursorPos", None)
            if callable(set_cursor):
                set_cursor(intent.x, intent.y)
        elif isinstance(intent, MoveBy):
            self._send_mouse_input(MOUSEEVENTF_MOVE, dx=intent.dx, dy=intent.dy)
        elif isinstance(intent, ButtonDown):
            self._handle_button(intent.button, down=True)
        elif isinstance(intent, ButtonUp):
            self._handle_button(intent.button, down=False)
        elif isinstance(intent, Click):
            for _ in range(intent.count):
                self._handle_button(intent.button, down=True)
                self._handle_button(intent.button, down=False)
        elif isinstance(intent, Scroll | Zoom):
            self._handle_scroll_or_zoom(intent)
        elif isinstance(intent, Key) and intent.chord == "ctrl":
            self._send_key_input(VK_CONTROL, is_up=not intent.down)
            if intent.down:
                self._held_items.add("key:ctrl")
            else:
                self._held_items.discard("key:ctrl")
        elif isinstance(intent, ReleaseAll):
            self.release_all()

    def apply(self, intents: Sequence[Intent]) -> None:
        with self._lock:
            for intent in intents:
                self._apply_one(intent)
