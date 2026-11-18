"""Linux uinput backend for mouse, keyboard, and gamepad input (M7).

Follows ARCHITECTURE §8 and INTERFACES §5:
- Uses `evdev` to create user-space input devices via `/dev/uinput`.
- Lazy import: gracefully handles systems without `evdev` or `/dev/uinput`.
- Full safety tracking via `held()` ledger and non-raising `release_all()`.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Sequence
from typing import Any

from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    Intent,
    Key,
    MoveBy,
    MoveTo,
    Pad,
    PadButton,
    ReleaseAll,
    Scroll,
    Trigger,
    Zoom,
)

logger = logging.getLogger(__name__)

# Fallback evdev event codes for headless/mock environments
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
SYN_REPORT = 0

REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08
REL_HWHEEL = 0x06

BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

BTN_SOUTH = 0x130  # A
BTN_EAST = 0x131  # B
BTN_NORTH = 0x133  # X
BTN_WEST = 0x134  # Y
BTN_TL = 0x136  # LB
BTN_TR = 0x137  # RB
BTN_SELECT = 0x13A  # Back
BTN_START = 0x13B  # Start

ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02  # Left trigger
ABS_RX = 0x03
ABS_RY = 0x04
ABS_RZ = 0x05  # Right trigger

KEY_LEFTCTRL = 29
DEADZONE_THRESHOLD = 0.05
MAX_AXIS_VAL = 32767
MAX_TRIG_VAL = 255

PAD_BUTTON_MAP: dict[PadButton, int] = {
    PadButton.A: BTN_SOUTH,
    PadButton.B: BTN_EAST,
    PadButton.X: BTN_NORTH,
    PadButton.Y: BTN_WEST,
    PadButton.LB: BTN_TL,
    PadButton.RB: BTN_TR,
    PadButton.BACK: BTN_SELECT,
    PadButton.START: BTN_START,
}


class LinuxUInputBackend:
    """Linux output backend driving /dev/uinput via evdev."""

    name = "linux_uinput"
    capabilities: frozenset[str] = frozenset({"mouse", "keyboard", "gamepad"})

    def __init__(self, uinput_device: object = None) -> None:
        self._custom_device = uinput_device
        self._device: Any = None
        self._lock = threading.RLock()
        self._held_keys: set[str] = set()
        self._is_open = False

    @property
    def is_open(self) -> bool:
        """Whether the backend uinput device is currently active."""
        with self._lock:
            return self._is_open

    def open(self) -> None:
        """Initialize uinput device or raise informative error."""
        with self._lock:
            if self._is_open:
                return

            if self._custom_device is not None:
                self._device = self._custom_device
                self._is_open = True
                return

            if sys.platform != "linux":
                raise RuntimeError(
                    "LinuxUInputBackend is only supported on Linux. "
                    f"Current platform: {sys.platform}"
                )

            try:
                import evdev  # noqa: PLC0415
            except ImportError as err:
                raise RuntimeError(
                    "LinuxUInputBackend requires the 'evdev' Python package. "
                    "Install with: pip install evdev"
                ) from err

            try:
                self._device = evdev.UInput(name="Aileron Virtual Controller")
                self._is_open = True
            except (PermissionError, FileNotFoundError, OSError) as err:
                raise RuntimeError(
                    "Failed to open /dev/uinput. Ensure the current user has write access "
                    "or udev rules are configured for uinput."
                ) from err

    def close(self) -> None:
        """Release all inputs and close the virtual device."""
        with self._lock:
            self.release_all()
            if self._device is not None and hasattr(self._device, "close"):
                try:
                    self._device.close()
                except Exception:
                    logger.debug("Exception closing uinput device", exc_info=True)
            self._device = None
            self._is_open = False

    def held(self) -> frozenset[str]:
        """Return currently held inputs."""
        with self._lock:
            return frozenset(self._held_keys)

    def release_all(self) -> None:
        """Idempotently release all held inputs."""
        with self._lock:
            if not self._is_open or self._device is None:
                self._held_keys.clear()
                return

            try:
                for token in list(self._held_keys):
                    self._release_token(token)

                self._write_event(EV_ABS, ABS_X, 0)
                self._write_event(EV_ABS, ABS_Y, 0)
                self._write_event(EV_ABS, ABS_Z, 0)
                self._write_event(EV_ABS, ABS_RX, 0)
                self._write_event(EV_ABS, ABS_RY, 0)
                self._write_event(EV_ABS, ABS_RZ, 0)
                self._syn()
            except Exception:
                logger.debug("Exception during uinput release_all", exc_info=True)
            finally:
                self._held_keys.clear()

    def apply(self, intents: Sequence[Intent]) -> None:
        """Apply approved intents to uinput device."""
        with self._lock:
            if not self._is_open or self._device is None:
                return

            for intent in intents:
                self._apply_one(intent)
            self._syn()

    def _apply_one(self, intent: Intent) -> None:
        if (
            self._apply_motion(intent)
            or self._apply_mouse_keys(intent)
            or self._apply_gamepad(intent)
        ):
            return
        if isinstance(intent, ReleaseAll):
            self.release_all()

    def _apply_motion(self, intent: Intent) -> bool:
        match intent:
            case MoveTo(x, y):
                self._write_event(EV_ABS, ABS_X, x)
                self._write_event(EV_ABS, ABS_Y, y)
                return True
            case MoveBy(dx, dy):
                self._write_event(EV_REL, REL_X, dx)
                self._write_event(EV_REL, REL_Y, dy)
                return True
            case Scroll(dx, dy):
                if dy != 0:
                    self._write_event(EV_REL, REL_WHEEL, int(dy))
                if dx != 0:
                    self._write_event(EV_REL, REL_HWHEEL, int(dx))
                return True
            case _:
                return False

    def _apply_mouse_keys(self, intent: Intent) -> bool:
        match intent:
            case ButtonDown(btn):
                code = self._btn_code(btn)
                token = f"mouse_{btn.name.lower()}"
                self._write_event(EV_KEY, code, 1)
                self._held_keys.add(token)
                return True
            case ButtonUp(btn):
                code = self._btn_code(btn)
                token = f"mouse_{btn.name.lower()}"
                self._write_event(EV_KEY, code, 0)
                self._held_keys.discard(token)
                return True
            case Click(btn, count):
                code = self._btn_code(btn)
                token = f"mouse_{btn.name.lower()}"
                for _ in range(count):
                    self._write_event(EV_KEY, code, 1)
                    self._syn()
                    self._write_event(EV_KEY, code, 0)
                    self._syn()
                self._held_keys.discard(token)
                return True
            case Zoom(steps):
                self._write_event(EV_KEY, KEY_LEFTCTRL, 1)
                self._write_event(EV_REL, REL_WHEEL, steps)
                self._syn()
                self._write_event(EV_KEY, KEY_LEFTCTRL, 0)
                return True
            case Key(chord, down):
                token = f"key_{chord.lower()}"
                code = KEY_LEFTCTRL if "ctrl" in chord.lower() else 1
                self._write_event(EV_KEY, code, 1 if down else 0)
                if down:
                    self._held_keys.add(token)
                else:
                    self._held_keys.discard(token)
                return True
            case _:
                return False

    def _apply_gamepad(self, intent: Intent) -> bool:
        match intent:
            case Axis(name, value):
                axis_code = {"lx": ABS_X, "ly": ABS_Y, "rx": ABS_RX, "ry": ABS_RY}.get(name, ABS_X)
                val_int = int(max(-1.0, min(1.0, value)) * MAX_AXIS_VAL)
                self._write_event(EV_ABS, axis_code, val_int)
                token = f"axis_{name}"
                if abs(value) > DEADZONE_THRESHOLD:
                    self._held_keys.add(token)
                else:
                    self._held_keys.discard(token)
                return True
            case Trigger(name, value):
                trig_code = ABS_RZ if name == "rt" else ABS_Z
                val_int = int(max(0.0, min(1.0, value)) * MAX_TRIG_VAL)
                self._write_event(EV_ABS, trig_code, val_int)
                token = f"trigger_{name}"
                if value > DEADZONE_THRESHOLD:
                    self._held_keys.add(token)
                else:
                    self._held_keys.discard(token)
                return True
            case Pad(button, down):
                code = PAD_BUTTON_MAP.get(button, BTN_SOUTH)
                token = f"pad_{button.name.lower()}"
                self._write_event(EV_KEY, code, 1 if down else 0)
                if down:
                    self._held_keys.add(token)
                else:
                    self._held_keys.discard(token)
                return True
            case _:
                return False

    def _btn_code(self, btn: Button) -> int:
        match btn:
            case Button.LEFT:
                return BTN_LEFT
            case Button.RIGHT:
                return BTN_RIGHT
            case Button.MIDDLE:
                return BTN_MIDDLE

    def _write_event(self, ev_type: int, code: int, value: int) -> None:
        if self._device is not None and hasattr(self._device, "write"):
            self._device.write(ev_type, code, value)

    def _syn(self) -> None:
        if self._device is not None:
            if hasattr(self._device, "syn"):
                self._device.syn()
            elif hasattr(self._device, "write"):
                self._device.write(EV_SYN, SYN_REPORT, 0)

    def _release_token(self, token: str) -> None:
        if token.startswith("mouse_"):
            btn_name = token[6:]
            code = (
                BTN_LEFT
                if btn_name == "left"
                else (BTN_RIGHT if btn_name == "right" else BTN_MIDDLE)
            )
            self._write_event(EV_KEY, code, 0)
        elif token.startswith("pad_"):
            pad_name = token[4:].upper()
            pad_btn = getattr(PadButton, pad_name, None)
            if pad_btn is not None:
                code = PAD_BUTTON_MAP.get(pad_btn, BTN_SOUTH)
                self._write_event(EV_KEY, code, 0)
        elif token.startswith("key_"):
            self._write_event(EV_KEY, KEY_LEFTCTRL, 0)
