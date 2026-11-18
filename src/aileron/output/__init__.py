"""Aileron output backends package (Windows).

Provides hardware, operating system, and mock backends:
- Base protocol: `OutputBackend`
- Windows Mouse & Keyboard: `WindowsMouseKeyboardBackend` (ctypes Win32 SendInput)
- Virtual Gamepad: `VGamepadBackend` (ViGEmBus Xbox 360 controller)
- Software Fallback: `KeyboardPwmGamepad` (PWM keyboard emulation)
- Safe Testing: `NullBackend`
"""

from aileron.output.base import OutputBackend
from aileron.output.gamepad import KeyboardPwmGamepad, VGamepadBackend
from aileron.output.null import NullBackend
from aileron.output.windows import WindowsMouseKeyboardBackend

__all__ = [
    "KeyboardPwmGamepad",
    "NullBackend",
    "OutputBackend",
    "VGamepadBackend",
    "WindowsMouseKeyboardBackend",
]
