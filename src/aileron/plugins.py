"""Plugin loader and entry point discovery for backends and gestures (M7).

Follows ARCHITECTURE §9 (Extensibility) & §11 (Security):
- Discovers backends via `aileron.backends` entry point group.
- Discovers gesture detectors via `aileron.gestures` entry point group.
- Trusted local environment only; third-party packages register standard entry points.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import TYPE_CHECKING

from aileron.output.base import OutputBackend
from aileron.output.gamepad import KeyboardPwmGamepad, VGamepadBackend
from aileron.output.linux import LinuxUInputBackend
from aileron.output.macos import MacosQuartzBackend
from aileron.output.null import NullBackend
from aileron.output.windows import WindowsMouseKeyboardBackend

if TYPE_CHECKING:
    from aileron.interfaces import GestureDetector

logger = logging.getLogger(__name__)

# Built-in backends provided by core Aileron package
BUILTIN_BACKENDS: dict[str, type[OutputBackend]] = {
    "null": NullBackend,
    "windows": WindowsMouseKeyboardBackend,
    "linux": LinuxUInputBackend,
    "macos": MacosQuartzBackend,
    "vgamepad": VGamepadBackend,
    "keyboard_pwm": KeyboardPwmGamepad,
}


def load_backend_plugins() -> dict[str, type[OutputBackend]]:
    """Discover all registered output backends from built-ins and entry points."""
    backends: dict[str, type[OutputBackend]] = dict(BUILTIN_BACKENDS)

    try:
        eps = importlib.metadata.entry_points(group="aileron.backends")
        for ep in eps:
            try:
                backend_cls = ep.load()
                backends[ep.name] = backend_cls
                logger.info("Loaded backend plugin '%s' from %s", ep.name, ep.value)
            except Exception:
                logger.warning(
                    "Failed to load backend plugin '%s' (%s)",
                    ep.name,
                    ep.value,
                    exc_info=True,
                )
    except Exception:
        logger.debug("Error querying aileron.backends entry points", exc_info=True)

    return backends


def load_gesture_plugins() -> dict[str, type[GestureDetector]]:
    """Discover all registered gesture detectors from entry points."""
    gestures: dict[str, type[GestureDetector]] = {}

    try:
        eps = importlib.metadata.entry_points(group="aileron.gestures")
        for ep in eps:
            try:
                detector_cls = ep.load()
                gestures[ep.name] = detector_cls
                logger.info("Loaded gesture plugin '%s' from %s", ep.name, ep.value)
            except Exception:
                logger.warning(
                    "Failed to load gesture plugin '%s' (%s)",
                    ep.name,
                    ep.value,
                    exc_info=True,
                )
    except Exception:
        logger.debug("Error querying aileron.gestures entry points", exc_info=True)

    return gestures
