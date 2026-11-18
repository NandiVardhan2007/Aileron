"""HUD window and display manager supporting Compact and Full modes (M6).

Follows CALIBRATION_UX §4 and SAFETY §8:
- Click-through transparent overlay (never steals focus or blocks OS input).
- Compact mode: minimal corner status chip.
- Full mode: complete telemetry, skeleton overlay, dwell rings, and cockpit axes.
- PySide6 optional integration with seamless OpenCV fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

from aileron.interfaces import HandFrame, SessionState
from aileron.modes.manager import ControlMode
from aileron.ui.overlay import draw_hud

if TYPE_CHECKING:
    from aileron.modes.yoke import YokeTelemetry

logger = logging.getLogger(__name__)


class HudMode(Enum):
    """Display density mode for HUD overlay."""

    COMPACT = "compact"
    FULL = "full"
    OFF = "off"


@dataclass(slots=True)
class HudState:
    """Telemetry snapshot displayed by the HUD."""

    session_state: SessionState = SessionState.DISARMED
    control_mode: ControlMode = ControlMode.POINTER
    fps: float = 0.0
    latency_ms: float = 0.0
    dwell_progress: dict[str, float] | None = None
    cockpit_telemetry: YokeTelemetry | None = None


class HudManager:
    """Coordinates HUD rendering across Compact, Full, and Click-through modes."""

    def __init__(self, mode: HudMode = HudMode.COMPACT) -> None:
        self.mode = mode
        self.state = HudState()

    def update_telemetry(
        self,
        session_state: SessionState,
        control_mode: ControlMode,
        fps: float,
        latency_ms: float,
        dwell_progress: dict[str, float] | None = None,
        cockpit_telemetry: YokeTelemetry | None = None,
    ) -> None:
        """Update internal telemetry state."""
        self.state.session_state = session_state
        self.state.control_mode = control_mode
        self.state.fps = fps
        self.state.latency_ms = latency_ms
        self.state.dwell_progress = dwell_progress
        self.state.cockpit_telemetry = cockpit_telemetry

    def render(self, canvas: np.ndarray, frame: HandFrame | None = None) -> np.ndarray:
        """Render HUD elements onto canvas frame."""
        if self.mode == HudMode.OFF:
            return canvas

        is_cockpit = self.state.control_mode == ControlMode.COCKPIT
        mode_str = "COCKPIT · YOKE" if is_cockpit else "POINTER"

        return draw_hud(
            canvas=canvas,
            session_state=self.state.session_state,
            mode_str=mode_str,
            hand_frame=frame,
            fps=self.state.fps if self.mode == HudMode.FULL else None,
            latency_ms=self.state.latency_ms if self.mode == HudMode.FULL else None,
            dwell_progress=self.state.dwell_progress,
        )
