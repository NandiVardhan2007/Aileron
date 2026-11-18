"""Pinch gesture finite state machines for clicks and drags (M2).

Implements:
- Hysteresis (pinch_on < pinch_off)
- Minimum pinch duration filter (min_pinch_ms) to reject noise
- Left click, double click, and drag FSM (tap_ms, dbl_ms)
- Right click (thumb + middle finger tap with conflict margin)
- Middle click (thumb + ring finger tap with finger coupling check)
- Click freeze indication during pending pinch
- Rate limiting per max_clicks_per_s
"""

from collections.abc import Sequence
from enum import Enum

from aileron.config import ClickConfig
from aileron.interfaces import GestureEvent, GestureKind, HandFeatures


class PinchState(Enum):
    """Pinch state machine states."""

    OPEN = "open"
    PINCH_PENDING = "pinch_pending"
    DRAGGING = "dragging"


class PinchKind(Enum):
    """Finger involved in pinch."""

    NONE = "none"
    INDEX = "index"
    MIDDLE = "middle"
    RING = "ring"
    PINKY = "pinky"


class PinchLeftDetector:
    """Left pinch detector handling single click, double click, and drag."""

    def __init__(self, config: ClickConfig) -> None:
        self.config = config
        self.state: PinchState = PinchState.OPEN
        self._pinch_start_ns: int = 0
        self._last_click_ns: int = 0
        self._last_emit_ns: int = 0
        self._min_interval_ns: int = int(1_000_000_000 / config.max_clicks_per_s)
        self._is_frozen: bool = False

    @property
    def is_cursor_frozen(self) -> bool:
        """True when click freeze damping should be applied to cursor."""
        return self._is_frozen

    def reset(self) -> None:
        """Reset state machine."""
        self.state = PinchState.OPEN
        self._pinch_start_ns = 0
        self._last_click_ns = 0
        self._last_emit_ns = 0
        self._is_frozen = False

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update FSM with current hand features."""
        if not feats or not feats[0].valid:
            if self.state == PinchState.DRAGGING:
                self.state = PinchState.OPEN
                self._is_frozen = False
                # Hand lost during drag -> release drag immediately (SAFE-02)
                return (GestureEvent(kind=GestureKind.DRAG_END, t_ns=t_ns, side=None),)
            self.state = PinchState.OPEN
            self._is_frozen = False
            return ()

        h = feats[0]
        r_index = h.pinch.get("index", 1.0)
        r_middle = h.pinch.get("middle", 1.0)

        middle_clear = (r_middle - r_index >= self.config.margin) or (
            r_middle >= self.config.pinch_off
        )

        if self.state == PinchState.OPEN:
            if r_index < self.config.pinch_on and middle_clear:
                self.state = PinchState.PINCH_PENDING
                self._pinch_start_ns = t_ns
                self._is_frozen = True
            return ()

        if self.state == PinchState.PINCH_PENDING:
            return self._update_pending(h, r_index, t_ns)

        if self.state == PinchState.DRAGGING and r_index > self.config.pinch_off:
            self.state = PinchState.OPEN
            self._is_frozen = False
            return (GestureEvent(kind=GestureKind.DRAG_END, t_ns=t_ns, side=h.side),)

        return ()

    def _update_pending(self, h: HandFeatures, r_index: float, t_ns: int) -> Sequence[GestureEvent]:
        """Handle transitions while in PINCH_PENDING state."""
        elapsed_ms = (t_ns - self._pinch_start_ns) / 1_000_000.0

        if r_index > self.config.pinch_off:
            self.state = PinchState.OPEN
            self._is_frozen = False

            if elapsed_ms < self.config.min_pinch_ms or elapsed_ms > self.config.tap_ms:
                return ()

            if self._last_emit_ns > 0 and (t_ns - self._last_emit_ns) < self._min_interval_ns:
                return ()

            interval_ms = (
                (t_ns - self._last_click_ns) / 1_000_000.0 if self._last_click_ns > 0 else 999999.0
            )

            if self._last_click_ns > 0 and interval_ms <= self.config.dbl_ms:
                self._last_click_ns = 0
                self._last_emit_ns = t_ns
                return (GestureEvent(kind=GestureKind.DOUBLE_CLICK, t_ns=t_ns, side=h.side),)

            self._last_click_ns = t_ns
            self._last_emit_ns = t_ns
            return (GestureEvent(kind=GestureKind.CLICK_LEFT, t_ns=t_ns, side=h.side),)

        if elapsed_ms >= self.config.tap_ms:
            self.state = PinchState.DRAGGING
            self._is_frozen = False  # Unfreeze so cursor can drag
            return (GestureEvent(kind=GestureKind.DRAG_START, t_ns=t_ns, side=h.side),)

        return ()


class PinchRightDetector:
    """Right click pinch detector (thumb + middle finger tap)."""

    def __init__(self, config: ClickConfig) -> None:
        self.config = config
        self.state: PinchState = PinchState.OPEN
        self._pinch_start_ns: int = 0
        self._last_emit_ns: int = 0
        self._min_interval_ns: int = int(1_000_000_000 / config.max_clicks_per_s)
        self._is_frozen: bool = False

    @property
    def is_cursor_frozen(self) -> bool:
        """True when click freeze damping should be applied to cursor."""
        return self._is_frozen

    def reset(self) -> None:
        """Reset state machine."""
        self.state = PinchState.OPEN
        self._pinch_start_ns = 0
        self._last_emit_ns = 0
        self._is_frozen = False

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update FSM with current hand features."""
        if not feats or not feats[0].valid:
            self.state = PinchState.OPEN
            self._is_frozen = False
            return ()

        h = feats[0]
        r_index = h.pinch.get("index", 1.0)
        r_middle = h.pinch.get("middle", 1.0)

        # Conflict margin check: middle finger must be closer than index
        index_clear = (r_index - r_middle >= self.config.margin) and (
            r_index >= self.config.pinch_off
        )

        events: list[GestureEvent] = []

        if self.state == PinchState.OPEN:
            if r_middle < self.config.pinch_on and index_clear:
                self.state = PinchState.PINCH_PENDING
                self._pinch_start_ns = t_ns
                self._is_frozen = True

        elif self.state == PinchState.PINCH_PENDING:
            elapsed_ms = (t_ns - self._pinch_start_ns) / 1_000_000.0

            if r_middle > self.config.pinch_off:
                self.state = PinchState.OPEN
                self._is_frozen = False

                if self.config.min_pinch_ms <= elapsed_ms <= self.config.tap_ms:
                    if (
                        self._last_emit_ns > 0
                        and (t_ns - self._last_emit_ns) < self._min_interval_ns
                    ):
                        return ()
                    self._last_emit_ns = t_ns
                    events.append(
                        GestureEvent(kind=GestureKind.CLICK_RIGHT, t_ns=t_ns, side=h.side)
                    )
            elif elapsed_ms > self.config.tap_ms:
                # Held past tap threshold without drag capability; cancel
                self.state = PinchState.OPEN
                self._is_frozen = False

        return tuple(events)


class PinchMiddleDetector:
    """Middle click pinch detector (thumb + ring finger tap)."""

    def __init__(self, config: ClickConfig) -> None:
        self.config = config
        self.state: PinchState = PinchState.OPEN
        self._pinch_start_ns: int = 0
        self._last_emit_ns: int = 0
        self._min_interval_ns: int = int(1_000_000_000 / config.max_clicks_per_s)
        self._is_frozen: bool = False

    @property
    def is_cursor_frozen(self) -> bool:
        """True when click freeze damping should be applied to cursor."""
        return self._is_frozen

    def reset(self) -> None:
        """Reset state machine."""
        self.state = PinchState.OPEN
        self._pinch_start_ns = 0
        self._last_emit_ns = 0
        self._is_frozen = False

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update FSM with current hand features."""
        if not feats or not feats[0].valid:
            self.state = PinchState.OPEN
            self._is_frozen = False
            return ()

        h = feats[0]
        r_index = h.pinch.get("index", 1.0)
        r_middle = h.pinch.get("middle", 1.0)
        r_ring = h.pinch.get("ring", 1.0)
        r_pinky = h.pinch.get("pinky", 1.0)

        # Ring finger must be pinched; index and middle must NOT be pinched
        fingers_clear = (
            (r_index >= self.config.pinch_off)
            and (r_middle >= self.config.pinch_off)
            and (r_middle - r_ring >= self.config.margin)
            and ((r_pinky >= self.config.pinch_off) or (r_pinky - r_ring >= self.config.margin))
        )

        events: list[GestureEvent] = []

        if self.state == PinchState.OPEN:
            if r_ring < self.config.pinch_on and fingers_clear:
                self.state = PinchState.PINCH_PENDING
                self._pinch_start_ns = t_ns
                self._is_frozen = True

        elif self.state == PinchState.PINCH_PENDING:
            elapsed_ms = (t_ns - self._pinch_start_ns) / 1_000_000.0

            if r_ring > self.config.pinch_off:
                self.state = PinchState.OPEN
                self._is_frozen = False

                if self.config.min_pinch_ms <= elapsed_ms <= self.config.tap_ms:
                    if (
                        self._last_emit_ns > 0
                        and (t_ns - self._last_emit_ns) < self._min_interval_ns
                    ):
                        return ()
                    self._last_emit_ns = t_ns
                    events.append(
                        GestureEvent(kind=GestureKind.CLICK_MIDDLE, t_ns=t_ns, side=h.side)
                    )
            elif elapsed_ms > self.config.tap_ms:
                self.state = PinchState.OPEN
                self._is_frozen = False

        return tuple(events)


class PinchGestureDetector:
    """Unified detector aggregating left, right, and middle pinch interactions."""

    name: str = "pinch"

    def __init__(self, config: ClickConfig) -> None:
        self.config = config
        self.left = PinchLeftDetector(config)
        self.right = PinchRightDetector(config)
        self.middle = PinchMiddleDetector(config)

    @property
    def is_cursor_frozen(self) -> bool:
        """True if any pinch detector is currently in PINCH_PENDING."""
        return (
            self.left.is_cursor_frozen
            or self.right.is_cursor_frozen
            or self.middle.is_cursor_frozen
        )

    def reset(self) -> None:
        """Reset all child detectors."""
        self.left.reset()
        self.right.reset()
        self.middle.reset()

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Update all child detectors and collect events."""
        events: list[GestureEvent] = []
        events.extend(self.left.update(feats, t_ns))
        events.extend(self.right.update(feats, t_ns))
        events.extend(self.middle.update(feats, t_ns))
        return tuple(events)
