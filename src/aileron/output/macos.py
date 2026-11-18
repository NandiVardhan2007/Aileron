"""macOS Quartz / CoreGraphics backend for mouse and keyboard input (M7).

Follows ARCHITECTURE §8 and INTERFACES §5:
- Uses macOS CoreGraphics / Quartz events via PyObjC.
- Lazy import: gracefully handles systems without Quartz or non-macOS platforms.
- Safety tracking via `held()` ledger and non-raising `release_all()`.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Sequence
from typing import Any

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

logger = logging.getLogger(__name__)

# Fallback CoreGraphics event constants
CG_EVENT_LEFT_MOUSE_DOWN = 1
CG_EVENT_LEFT_MOUSE_UP = 2
CG_EVENT_RIGHT_MOUSE_DOWN = 3
CG_EVENT_RIGHT_MOUSE_UP = 4
CG_EVENT_MOUSE_MOVED = 5
CG_EVENT_OTHER_MOUSE_DOWN = 25
CG_EVENT_OTHER_MOUSE_UP = 26
CG_SCROLL_EVENT_UNIT_LINE = 1
CG_HID_EVENT_TAP = 0


class MacosQuartzBackend:
    """macOS output backend driving Quartz CoreGraphics events."""

    name = "macos_quartz"
    capabilities: frozenset[str] = frozenset({"mouse", "keyboard"})

    def __init__(self, cg_module: object = None) -> None:
        self._custom_cg = cg_module
        self._cg: Any = None
        self._lock = threading.RLock()
        self._held_keys: set[str] = set()
        self._is_open = False
        self._cur_x: float = 0.0
        self._cur_y: float = 0.0

    @property
    def is_open(self) -> bool:
        """Whether the backend Quartz event system is currently active."""
        with self._lock:
            return self._is_open

    def open(self) -> None:
        """Initialize Quartz access or raise informative error."""
        with self._lock:
            if self._is_open:
                return

            if self._custom_cg is not None:
                self._cg = self._custom_cg
                self._is_open = True
                return

            if sys.platform != "darwin":
                raise RuntimeError(
                    "MacosQuartzBackend is only supported on macOS (darwin). "
                    f"Current platform: {sys.platform}"
                )

            try:
                from Quartz import CoreGraphics as CG  # noqa: PLC0415, N817

                self._cg = CG
                self._is_open = True
            except ImportError as err:
                raise RuntimeError(
                    "MacosQuartzBackend requires the 'pyobjc-framework-Quartz' package. "
                    "Install with: pip install pyobjc-framework-Quartz"
                ) from err

    def close(self) -> None:
        """Release all inputs and reset backend state."""
        with self._lock:
            self.release_all()
            self._cg = None
            self._is_open = False

    def held(self) -> frozenset[str]:
        """Return currently held inputs."""
        with self._lock:
            return frozenset(self._held_keys)

    def release_all(self) -> None:
        """Idempotently release all held mouse buttons and keys."""
        with self._lock:
            if not self._is_open or self._cg is None:
                self._held_keys.clear()
                return

            try:
                for token in list(self._held_keys):
                    self._release_token(token)
            except Exception:
                logger.debug("Exception during Quartz release_all", exc_info=True)
            finally:
                self._held_keys.clear()

    def apply(self, intents: Sequence[Intent]) -> None:
        """Apply approved intents to macOS Quartz event queue."""
        with self._lock:
            if not self._is_open or self._cg is None:
                return

            for intent in intents:
                self._apply_one(intent)

    def _apply_one(self, intent: Intent) -> None:
        if (
            self._apply_motion(intent)
            or self._apply_buttons(intent)
            or self._apply_keyboard(intent)
        ):
            return
        if isinstance(intent, ReleaseAll):
            self.release_all()

    def _apply_motion(self, intent: Intent) -> bool:
        match intent:
            case MoveTo(x, y):
                self._cur_x = float(x)
                self._cur_y = float(y)
                self._post_mouse_event(CG_EVENT_MOUSE_MOVED, self._cur_x, self._cur_y)
                return True
            case MoveBy(dx, dy):
                self._cur_x += float(dx)
                self._cur_y += float(dy)
                self._post_mouse_event(CG_EVENT_MOUSE_MOVED, self._cur_x, self._cur_y)
                return True
            case Scroll(dx, dy):
                self._post_scroll_event(int(dy), int(dx))
                return True
            case _:
                return False

    def _apply_buttons(self, intent: Intent) -> bool:
        match intent:
            case ButtonDown(btn):
                token = f"mouse_{btn.name.lower()}"
                ev_type = self._btn_event_type(btn, down=True)
                self._post_mouse_event(ev_type, self._cur_x, self._cur_y)
                self._held_keys.add(token)
                return True
            case ButtonUp(btn):
                token = f"mouse_{btn.name.lower()}"
                ev_type = self._btn_event_type(btn, down=False)
                self._post_mouse_event(ev_type, self._cur_x, self._cur_y)
                self._held_keys.discard(token)
                return True
            case Click(btn, count):
                token = f"mouse_{btn.name.lower()}"
                down_ev = self._btn_event_type(btn, down=True)
                up_ev = self._btn_event_type(btn, down=False)
                for _ in range(count):
                    self._post_mouse_event(down_ev, self._cur_x, self._cur_y)
                    self._post_mouse_event(up_ev, self._cur_x, self._cur_y)
                self._held_keys.discard(token)
                return True
            case _:
                return False

    def _apply_keyboard(self, intent: Intent) -> bool:
        match intent:
            case Zoom(steps):
                self._held_keys.add("key_ctrl")
                self._post_scroll_event(steps, 0)
                self._held_keys.discard("key_ctrl")
                return True
            case Key(chord, down):
                token = f"key_{chord.lower()}"
                self._post_key_event(chord, down)
                if down:
                    self._held_keys.add(token)
                else:
                    self._held_keys.discard(token)
                return True
            case _:
                return False

    def _btn_event_type(self, btn: Button, down: bool) -> int:
        match btn:
            case Button.LEFT:
                return CG_EVENT_LEFT_MOUSE_DOWN if down else CG_EVENT_LEFT_MOUSE_UP
            case Button.RIGHT:
                return CG_EVENT_RIGHT_MOUSE_DOWN if down else CG_EVENT_RIGHT_MOUSE_UP
            case Button.MIDDLE:
                return CG_EVENT_OTHER_MOUSE_DOWN if down else CG_EVENT_OTHER_MOUSE_UP

    def _post_mouse_event(self, ev_type: int, x: float, y: float) -> None:
        if self._cg is not None and hasattr(self._cg, "CGEventCreateMouseEvent"):
            ev = self._cg.CGEventCreateMouseEvent(None, ev_type, (x, y), 0)
            if hasattr(self._cg, "CGEventPost"):
                self._cg.CGEventPost(CG_HID_EVENT_TAP, ev)

    def _post_scroll_event(self, lines_y: int, lines_x: int) -> None:
        if self._cg is not None and hasattr(self._cg, "CGEventCreateScrollWheelEvent2"):
            ev = self._cg.CGEventCreateScrollWheelEvent2(
                None, CG_SCROLL_EVENT_UNIT_LINE, 2, lines_y, lines_x
            )
            if hasattr(self._cg, "CGEventPost"):
                self._cg.CGEventPost(CG_HID_EVENT_TAP, ev)

    def _post_key_event(self, chord: str, down: bool) -> None:
        if self._cg is not None and hasattr(self._cg, "CGEventCreateKeyboardEvent"):
            code = 59 if "ctrl" in chord.lower() else 0
            ev = self._cg.CGEventCreateKeyboardEvent(None, code, down)
            if hasattr(self._cg, "CGEventPost"):
                self._cg.CGEventPost(CG_HID_EVENT_TAP, ev)

    def _release_token(self, token: str) -> None:
        if token.startswith("mouse_"):
            btn_name = token[6:]
            btn = getattr(Button, btn_name.upper(), Button.LEFT)
            ev_type = self._btn_event_type(btn, down=False)
            self._post_mouse_event(ev_type, self._cur_x, self._cur_y)
        elif token.startswith("key_"):
            self._post_key_event(token[4:], down=False)
