"""Gamepad output backends: VGamepad (Windows ViGEmBus) and KeyboardPwmGamepad fallback (M5).

Follows COCKPIT_MODE §6 and SAFETY §1, §4, §8:
- Lazy import of vgamepad; informative error if driver missing.
- KeyboardPwmGamepad universal software fallback.
- Fail-closed release_all() guarantees empty held set on exit.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Sequence
from typing import Any

from aileron.interfaces import (
    Axis,
    Intent,
    Pad,
    PadButton,
    ReleaseAll,
    Trigger,
)
from aileron.safety.ledger import HeldInputLedger

logger = logging.getLogger(__name__)

PWM_STEER_DEADZONE = 0.15
PWM_TRIGGER_THRESHOLD = 0.10


class VGamepadBackend:
    """Windows virtual Xbox 360 controller backend using vgamepad / ViGEmBus."""

    name: str = "vgamepad"
    capabilities: frozenset[str] = frozenset({"gamepad"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._is_open = False
        self._gamepad: Any = None
        self._vg: Any = None
        self.ledger = HeldInputLedger()

    @property
    def is_open(self) -> bool:
        """Whether virtual gamepad device is opened."""
        return self._is_open

    def open(self) -> None:
        """Instantiate virtual Xbox 360 gamepad controller."""
        with self._lock:
            if self._is_open:
                return
            try:
                import vgamepad as vg  # noqa: PLC0415

                self._vg = vg
                self._gamepad = vg.VX360Gamepad()
                self._is_open = True
                logger.info("VGamepadBackend initialized virtual Xbox 360 controller.")
            except (ImportError, Exception) as exc:
                self._is_open = False
                raise RuntimeError(
                    f"ViGEmBus / vgamepad driver is unavailable on this system: {exc}. "
                    "Install ViGEmBus driver or use KeyboardPwmGamepad / NullBackend."
                ) from exc

    def close(self) -> None:
        """Close virtual gamepad and release all inputs."""
        self.release_all()
        with self._lock:
            if self._gamepad is not None:
                with contextlib.suppress(Exception):
                    del self._gamepad
                self._gamepad = None
            self._is_open = False

    def release_all(self) -> None:
        """Neutralize all axes, triggers, and buttons."""
        with self._lock:
            self.ledger.drain_and_create_releases()
            if self._gamepad is not None:
                try:
                    self._gamepad.reset()
                    self._gamepad.update()
                except Exception:
                    logger.exception("Error resetting virtual gamepad during release_all")

    def held(self) -> frozenset[str]:
        """Return set of currently held inputs."""
        with self._lock:
            return self.ledger.held()

    def apply(self, intents: Sequence[Intent]) -> None:
        """Apply gamepad axis, trigger, and button intents."""
        with self._lock:
            if not self._is_open or self._gamepad is None:
                return

            needs_update = False
            for intent in intents:
                match intent:
                    case ReleaseAll():
                        self.release_all()
                        return
                    case Axis(name="lx", value=val):
                        self._gamepad.left_joystick_float(
                            x_value_float=float(val), y_value_float=0.0
                        )
                        self.ledger.record(intent)
                        needs_update = True
                    case Axis(name="rx", value=val):
                        self._gamepad.right_joystick_float(
                            x_value_float=float(val), y_value_float=0.0
                        )
                        self.ledger.record(intent)
                        needs_update = True
                    case Trigger(name="rt", value=val):
                        self._gamepad.right_trigger_float(value_float=float(val))
                        self.ledger.record(intent)
                        needs_update = True
                    case Trigger(name="lt", value=val):
                        self._gamepad.left_trigger_float(value_float=float(val))
                        self.ledger.record(intent)
                        needs_update = True
                    case Pad(button=btn, down=down):
                        self._apply_button(btn, down)
                        self.ledger.record(intent)
                        needs_update = True
                    case _:
                        pass

            if needs_update:
                self._gamepad.update()

    def _apply_button(self, btn: PadButton, down: bool) -> None:
        """Map PadButton to vgamepad XUSB_BUTTON flags."""
        vg = self._vg
        button_map = {
            PadButton.A: vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
            PadButton.B: vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
            PadButton.X: vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
            PadButton.Y: vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
            PadButton.LB: vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER,
            PadButton.RB: vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER,
            PadButton.START: vg.XUSB_BUTTON.XUSB_GAMEPAD_START,
            PadButton.BACK: vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK,
            PadButton.DPAD_UP: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP,
            PadButton.DPAD_DOWN: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN,
            PadButton.DPAD_LEFT: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT,
            PadButton.DPAD_RIGHT: vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT,
        }
        mask = button_map.get(btn)
        if mask is not None:
            if down:
                self._gamepad.press_button(button=mask)
            else:
                self._gamepad.release_button(button=mask)


class KeyboardPwmGamepad:
    """Universal fallback mapping analog gamepad axes to keyboard PWM pulses."""

    name: str = "keyboard_pwm"
    capabilities: frozenset[str] = frozenset({"gamepad", "keyboard"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._is_open = False
        self.ledger = HeldInputLedger()
        self.active_keys: set[str] = set()

    @property
    def is_open(self) -> bool:
        """Whether backend is open."""
        return self._is_open

    def open(self) -> None:
        """Open backend."""
        with self._lock:
            self._is_open = True

    def close(self) -> None:
        """Close backend and neutralize keys."""
        self.release_all()
        with self._lock:
            self._is_open = False

    def release_all(self) -> None:
        """Neutralize all pressed keys."""
        with self._lock:
            self.active_keys.clear()
            self.ledger.drain_and_create_releases()

    def held(self) -> frozenset[str]:
        """Return set of currently held keys."""
        with self._lock:
            return frozenset(self.active_keys)

    def apply(self, intents: Sequence[Intent]) -> None:
        """Convert analog axes and triggers to discrete key state."""
        with self._lock:
            if not self._is_open:
                return

            for intent in intents:
                if isinstance(intent, ReleaseAll):
                    self.release_all()
                    return
                self._apply_pwm_intent(intent)

    def _apply_pwm_intent(self, intent: Intent) -> None:
        match intent:
            case Axis(name="lx", value=val):
                self.ledger.record(intent)
                self.active_keys.discard("a")
                self.active_keys.discard("d")
                if val < -PWM_STEER_DEADZONE:
                    self.active_keys.add("a")  # steer left
                elif val > PWM_STEER_DEADZONE:
                    self.active_keys.add("d")  # steer right
            case Trigger(name="rt", value=val):
                self.ledger.record(intent)
                if val > PWM_TRIGGER_THRESHOLD:
                    self.active_keys.add("w")  # throttle
                else:
                    self.active_keys.discard("w")
            case Trigger(name="lt", value=val):
                self.ledger.record(intent)
                if val > PWM_TRIGGER_THRESHOLD:
                    self.active_keys.add("s")  # brake
                else:
                    self.active_keys.discard("s")
            case _:
                pass
