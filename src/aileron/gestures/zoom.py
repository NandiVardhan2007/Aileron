"""Two-hand pinch zoom detector (M3).

Implements G-08 and SIGNAL_PROCESSING §7:
- Requires both hands pinching index simultaneously for >= 80 ms
- Tracks distance D between hands normalized by max palm_size
- Emits Zoom(±1) steps per 6% fractional spacing change, rebasing D0
- Spreading hands zooms in (+), bringing hands together zooms out (-)
"""

import math
from collections.abc import Sequence
from enum import Enum

from aileron.config import ClickConfig, ZoomConfig
from aileron.interfaces import GestureEvent, GestureKind, HandFeatures

MIN_ZOOM_HANDS = 2


class ZoomState(Enum):
    """Zoom detector state."""

    IDLE = "idle"
    PENDING = "pending"
    ZOOMING = "zooming"


class ZoomDetector:
    """Detects simultaneous two-hand pinch zoom and emits discrete zoom step intents."""

    name: str = "zoom"

    def __init__(self, zoom_cfg: ZoomConfig, click_cfg: ClickConfig) -> None:
        self.config = zoom_cfg
        self.click_cfg = click_cfg
        self.state: ZoomState = ZoomState.IDLE
        self._start_ns: int = 0
        self._d0: float | None = None
        self.zoom_steps_delta: int = 0

    def reset(self) -> None:
        """Reset zoom state."""
        self.state = ZoomState.IDLE
        self._start_ns = 0
        self._d0 = None
        self.zoom_steps_delta = 0

    def _both_pinching(
        self, feats: Sequence[HandFeatures]
    ) -> tuple[HandFeatures, HandFeatures] | None:
        """Verify two valid hands are both currently pinching their index finger."""
        valid_hands = [f for f in feats if f.valid]
        if len(valid_hands) < MIN_ZOOM_HANDS:
            return None

        # Look for left and right hands
        h1, h2 = valid_hands[0], valid_hands[1]
        p1 = h1.pinch.get("index", 1.0)
        p2 = h2.pinch.get("index", 1.0)

        # Hysteresis threshold: pinch_off if zooming, pinch_on if idle
        thresh = (
            self.click_cfg.pinch_off if self.state == ZoomState.ZOOMING else self.click_cfg.pinch_on
        )
        if p1 < thresh and p2 < thresh:
            return h1, h2
        return None

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update zoom state machine across all present hands."""
        self.zoom_steps_delta = 0
        hands = self._both_pinching(feats)

        events: list[GestureEvent] = []

        if self.state == ZoomState.IDLE:
            if hands is not None:
                self.state = ZoomState.PENDING
                self._start_ns = t_ns

        elif self.state == ZoomState.PENDING:
            if hands is None:
                self.reset()
            else:
                elapsed_ms = (t_ns - self._start_ns) / 1_000_000.0
                if elapsed_ms >= self.config.require_both_pinch_ms:
                    self.state = ZoomState.ZOOMING
                    h1, h2 = hands
                    self._d0 = self._compute_distance(h1, h2)
                    events.append(GestureEvent(kind=GestureKind.ZOOM_START, t_ns=t_ns, side=None))

        elif self.state == ZoomState.ZOOMING:
            if hands is None:
                self.reset()
                return (GestureEvent(kind=GestureKind.ZOOM_END, t_ns=t_ns, side=None),)

            h1, h2 = hands
            current_d = self._compute_distance(h1, h2)

            if self._d0 is not None and self._d0 > 0.0:
                delta_fraction = (current_d - self._d0) / self._d0
                step_frac = self.config.step_fraction

                if abs(delta_fraction) >= step_frac:
                    steps = int(delta_fraction / step_frac)
                    if steps != 0:
                        self.zoom_steps_delta = steps
                        # Rebase D0 per SIGNAL_PROCESSING §7
                        self._d0 = current_d

        return tuple(events)

    def _compute_distance(self, h1: HandFeatures, h2: HandFeatures) -> float:
        """Compute normalized distance between two hands in palm units."""
        dx = h1.anchor[0] - h2.anchor[0]
        dy = h1.anchor[1] - h2.anchor[1]
        scale = max(1e-4, h1.palm_size, h2.palm_size)
        return float(math.hypot(dx, dy) / scale)
