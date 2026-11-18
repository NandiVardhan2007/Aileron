"""Accessibility options and motor assistance modes (M6).

Follows CALIBRATION_UX §5 and SAFETY H12-H13:
- Stability mode: heavier One Euro smoothing, wider pinch thresholds, longer dwell times.
- Dwell click: hover-to-click timer for users unable to perform pinch gestures.
- Reduced motion: disables animations and ensures no flashing > 3 Hz (SAFETY H13).
- Audio cues: accessibility tone notifications on state changes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from aileron.config import AileronConfig
from aileron.interfaces import Button, Click, Intent, MoveTo

ONE_SEC_NS = 1_000_000_000


@dataclass(slots=True)
class DwellClickDetector:
    """Hover-to-click detector emitting Click(LEFT) when cursor remains stationary."""

    dwell_ms: int = 600
    radius_px: float = 15.0
    _anchor: tuple[int, int] | None = None
    _dwell_start_ns: int | None = None
    _clicked: bool = False

    def reset(self) -> None:
        """Reset dwell timer."""
        self._anchor = None
        self._dwell_start_ns = None
        self._clicked = False

    def update(self, cursor_pos: tuple[int, int] | None, t_ns: int) -> list[Intent]:
        """Check if cursor has dwelled within radius_px for dwell_ms."""
        if cursor_pos is None:
            self.reset()
            return []

        cx, cy = cursor_pos
        if self._anchor is None:
            self._anchor = (cx, cy)
            self._dwell_start_ns = t_ns
            self._clicked = False
            return []

        # Distance from initial dwell anchor
        dist = math.hypot(cx - self._anchor[0], cy - self._anchor[1])
        if dist > self.radius_px:
            # Moved beyond radius -> reset anchor
            self._anchor = (cx, cy)
            self._dwell_start_ns = t_ns
            self._clicked = False
            return []

        # Cursor within radius: check elapsed dwell time
        if self._dwell_start_ns is not None and not self._clicked:
            elapsed_ms = (t_ns - self._dwell_start_ns) / 1_000_000.0
            if elapsed_ms >= self.dwell_ms:
                self._clicked = True
                return [Click(button=Button.LEFT, count=1)]

        return []


class AccessibilityManager:
    """Coordinates motor assistance, stability overrides, and dwell click."""

    def __init__(self, config: AileronConfig) -> None:
        self.config = config
        self.dwell_click = DwellClickDetector(
            dwell_ms=config.accessibility.dwell_click_ms
            if hasattr(config.accessibility, "dwell_click_ms")
            else 600
        )

    def apply_stability_mode_overrides(self) -> None:
        """Tune configuration parameters for users with tremor or reduced mobility."""
        # Heavier filter smoothing (lower cutoff, moderate beta)
        self.config.filters.cursor.min_cutoff = 0.6
        self.config.filters.cursor.beta = 4.0

        # Wider pinch hysteresis band
        self.config.click.pinch_on = 0.28
        self.config.click.pinch_off = 0.40

        # Extended dwell times
        self.config.session.clutch_ms = 600
        self.config.session.resume_ms = 600

    def process(
        self,
        candidate_intents: Sequence[Intent],
        t_ns: int,
    ) -> list[Intent]:
        """Apply accessibility processing, including dwell click injection."""
        out = list(candidate_intents)

        # If dwell click is enabled, extract cursor position from MoveTo
        if (
            hasattr(self.config.accessibility, "dwell_click")
            and self.config.accessibility.dwell_click
        ):
            move = next((i for i in out if isinstance(i, MoveTo)), None)
            cursor_pos = (move.x, move.y) if move is not None else None
            dwell_intents = self.dwell_click.update(cursor_pos, t_ns)
            out.extend(dwell_intents)

        return out
