"""Aileron output backends package.

Provides hardware, operating system, and mock backends:
- Base protocol: `OutputBackend`
- Windows: `WindowsMouseKeyboardBackend` (ctypes Win32 SendInput)
- Linux: `LinuxUInputBackend` (evdev /dev/uinput)
- Gamepad: `VGamepadBackend` (ViGEmBus Xbox 360 controller)
- Software fallback: `KeyboardPwmGamepad`
- Safe recording/testing: `NullBackend`
"""

from aileron.output.base import OutputBackend
from aileron.output.gamepad import KeyboardPwmGamepad, VGamepadBackend
from aileron.output.linux import LinuxUInputBackend
from aileron.output.null import NullBackend
from aileron.output.windows import WindowsMouseKeyboardBackend

__all__ = [
    "KeyboardPwmGamepad",
    "LinuxUInputBackend",
    "NullBackend",
    "OutputBackend",
    "VGamepadBackend",
    "WindowsMouseKeyboardBackend",
]
