"""OS-level global kill switch running on its own dedicated thread (SAFE-01)."""

import ctypes
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
VK_ESCAPE = 0x1B
HOTKEY_ID = 1001
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class KillSwitchListener:
    """Listens for global emergency hotkey (Ctrl+Alt+Esc) on dedicated thread."""

    def __init__(
        self,
        on_kill: Callable[[], None],
        user32_mock: object | None = None,
    ) -> None:
        self.on_kill = on_kill
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._lock = threading.Lock()
        win_dll = getattr(ctypes, "windll", None)
        self._user32 = (
            user32_mock
            if user32_mock is not None
            else (
                getattr(win_dll, "user32", None)
                if win_dll is not None and sys.platform == "win32"
                else None
            )
        )
        self._thread_id: int | None = None

    def start(self) -> None:
        """Launch the hotkey listener thread."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._run,
                name="aileron-kill-switch",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Stop hotkey thread and unregister hotkey."""
        with self._lock:
            self._running = False
            if self._thread_id and self._user32:
                post_msg = getattr(self._user32, "PostThreadMessageW", None)
                if callable(post_msg):
                    post_msg(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def trigger_manually(self) -> None:
        """Manually trigger kill action (e.g. from --panic or unit test)."""
        self.on_kill()

    def _run(self) -> None:
        if self._user32 is None:
            while self._running:
                threading.Event().wait(0.5)
            return

        win_dll = getattr(ctypes, "windll", None)
        kernel32 = getattr(win_dll, "kernel32", None) if win_dll is not None else None
        if kernel32:
            with self._lock:
                self._thread_id = kernel32.GetCurrentThreadId()

        modifiers = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
        reg_hotkey = getattr(self._user32, "RegisterHotKey", None)
        if callable(reg_hotkey):
            reg_hotkey(None, HOTKEY_ID, modifiers, VK_ESCAPE)

        unreg_hotkey = getattr(self._user32, "UnregisterHotKey", None)
        get_msg = getattr(self._user32, "GetMessageW", None)

        try:
            msg = wintypes.MSG()
            while self._running and callable(get_msg):
                res = get_msg(ctypes.byref(msg), None, 0, 0)
                if res <= 0:
                    break
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.on_kill()
        finally:
            if callable(unreg_hotkey):
                unreg_hotkey(None, HOTKEY_ID)
