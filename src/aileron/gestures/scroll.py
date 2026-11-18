"""V-sign joystick scroll detector (M3).

Implements G-07 and SIGNAL_PROCESSING §6:
- Joystick displacement from initial anchor a0 drives scroll rate
- Progressive power curve (x^1.5 default) with deadzone
- Horizontal and vertical scroll rate calculation
- Hysteresis on finger extension and V-sign gap
- Hold dwell before scrolling begins (hold_ms = 120 ms)
- Cursor freeze during scrolling
"""

from collections.abc import Sequence
from enum import Enum

from aileron.config import FingersConfig, ScrollConfig
from aileron.interfaces import GestureEvent, GestureKind, HandFeatures

THUMB_CLEAR_PINCH_RATIO = 0.5


class ScrollState(Enum):
    """Scroll detector states."""

    IDLE = "idle"
    PENDING = "pending"
    SCROLLING = "scrolling"


class ScrollDetector:
    """Detects V-sign pose and emits continuous joystick scroll rates."""

    name: str = "scroll"

    def __init__(self, config: ScrollConfig, fingers_cfg: FingersConfig) -> None:
        self.config = config
        self.fingers_cfg = fingers_cfg
        self.state: ScrollState = ScrollState.IDLE
        self._pose_start_ns: int = 0
        self._a0: tuple[float, float] | None = None
        self._last_t_ns: int = 0
        self.scroll_rate: tuple[float, float] = (0.0, 0.0)
        self.lines_delta: tuple[float, float] = (0.0, 0.0)

        # Hysteresis defaults per GESTURES.md
        self._gap_on = 0.30
        self._gap_off = 0.20

    @property
    def is_cursor_frozen(self) -> bool:
        """True when scroll is pending or active to prevent cursor drift."""
        return self.state in (ScrollState.PENDING, ScrollState.SCROLLING)

    def reset(self) -> None:
        """Reset state machine."""
        self.state = ScrollState.IDLE
        self._pose_start_ns = 0
        self._a0 = None
        self._last_t_ns = 0
        self.scroll_rate = (0.0, 0.0)
        self.lines_delta = (0.0, 0.0)

    def is_v_sign(self, h: HandFeatures) -> bool:
        """Evaluate V-sign finger state with hysteresis."""
        curls = h.curl
        pinches = h.pinch

        # Index and middle extended
        idx_ext = curls.get("index", 0.0)
        mid_ext = curls.get("middle", 0.0)
        ext_thresh = (
            self.fingers_cfg.ext_off if self.state != ScrollState.IDLE else self.fingers_cfg.ext_on
        )
        if idx_ext < ext_thresh or mid_ext < ext_thresh:
            return False

        # Ring and pinky curled
        rng_ext = curls.get("ring", 1.0)
        pnk_ext = curls.get("pinky", 1.0)
        curl_thresh = (
            self.fingers_cfg.ext_on if self.state != ScrollState.IDLE else self.fingers_cfg.ext_off
        )
        if rng_ext > curl_thresh or pnk_ext > curl_thresh:
            return False

        # Thumb far from fingertips (conflict matrix)
        if (
            pinches.get("index", 1.0) < THUMB_CLEAR_PINCH_RATIO
            or pinches.get("middle", 1.0) < THUMB_CLEAR_PINCH_RATIO
        ):
            return False

        # V-gap hysteresis check
        gap_thresh = self._gap_off if self.state != ScrollState.IDLE else self._gap_on
        return h.v_gap >= gap_thresh

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update scroll FSM from primary hand features."""
        self.lines_delta = (0.0, 0.0)

        if not feats or not feats[0].valid:
            if self.state == ScrollState.SCROLLING:
                self.reset()
                return (GestureEvent(kind=GestureKind.SCROLL_END, t_ns=t_ns, side=None),)
            self.reset()
            return ()

        h = feats[0]
        v_matched = self.is_v_sign(h)

        events: list[GestureEvent] = []

        if self.state == ScrollState.IDLE:
            if v_matched:
                self.state = ScrollState.PENDING
                self._pose_start_ns = t_ns
                self._last_t_ns = t_ns

        elif self.state == ScrollState.PENDING:
            if not v_matched:
                self.reset()
            else:
                elapsed_ms = (t_ns - self._pose_start_ns) / 1_000_000.0
                if elapsed_ms >= self.config.hold_ms:
                    self.state = ScrollState.SCROLLING
                    self._a0 = h.anchor
                    self._last_t_ns = t_ns
                    events.append(
                        GestureEvent(kind=GestureKind.SCROLL_START, t_ns=t_ns, side=h.side)
                    )

        elif self.state == ScrollState.SCROLLING:
            if not v_matched:
                self.reset()
                return (GestureEvent(kind=GestureKind.SCROLL_END, t_ns=t_ns, side=h.side),)

            # Compute rates based on displacement from anchor a0
            if self._a0 is not None and h.palm_size > 0.0:
                dx_palm = (h.anchor[0] - self._a0[0]) / h.palm_size
                # Up in screen is negative y in image, which scrolls up (positive lines)
                dy_palm = -(h.anchor[1] - self._a0[1]) / h.palm_size

                rate_x = self._compute_rate(dx_palm)
                rate_y = self._compute_rate(dy_palm)
                self.scroll_rate = (rate_x, rate_y)

                # Incremental lines
                dt_s = max(0.001, (t_ns - self._last_t_ns) / 1_000_000_000.0)
                self._last_t_ns = t_ns
                self.lines_delta = (rate_x * dt_s, rate_y * dt_s)

        return tuple(events)

    def _compute_rate(self, disp: float) -> float:
        """Apply deadzone, power curve, and rate limit per SIGNAL_PROCESSING §6."""
        excess = max(abs(disp) - self.config.deadzone, 0.0)
        if excess <= 0.0:
            return 0.0
        rate = (excess**self.config.power) * self.config.gain
        clamped_rate = float(min(rate, self.config.max_lines_per_s))
        return -clamped_rate if disp < 0.0 else clamped_rate
