"""Gesture engine orchestrating detectors, primary-hand tracking, and intent generation."""

from collections.abc import Sequence
from typing import ClassVar

from aileron.config import AileronConfig
from aileron.filters.one_euro import OneEuroFilter2D
from aileron.gestures.pinch import PinchGestureDetector
from aileron.interfaces import (
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    GestureDetector,
    GestureEvent,
    GestureKind,
    GestureOutput,
    HandFeatures,
    HandFrame,
    Intent,
    Side,
    Signals,
)
from aileron.mapping.cursor import CursorMapper


class PrimaryHandTracker:
    """Tracks sticky primary hand selection per SIG-11 and SIGNAL_PROCESSING §11."""

    def __init__(self, hand_lost_ms: int = 150) -> None:
        self.hand_lost_ms = hand_lost_ms
        self.locked_side: Side | None = None
        self._last_seen_ns: int = 0

    def reset(self) -> None:
        """Reset sticky hand lock."""
        self.locked_side = None
        self._last_seen_ns = 0

    def select(self, feats: Sequence[HandFeatures], t_ns: int) -> HandFeatures | None:
        """Select primary hand with sticky lock and palm_size tie-breaking."""
        valid_feats = [f for f in feats if f.valid]
        if not valid_feats:
            if self.locked_side is not None:
                elapsed_ms = (t_ns - self._last_seen_ns) / 1_000_000.0
                if elapsed_ms > self.hand_lost_ms:
                    self.locked_side = None
            return None

        # If already locked, stick to that side if still present
        if self.locked_side is not None:
            for f in valid_feats:
                if f.side == self.locked_side:
                    self._last_seen_ns = t_ns
                    return f

            # Locked hand not in this frame; check timeout
            elapsed_ms = (t_ns - self._last_seen_ns) / 1_000_000.0
            if elapsed_ms > self.hand_lost_ms:
                self.locked_side = None
            else:
                return None

        # Select new primary hand: tie-break by largest palm size
        best_hand = max(valid_feats, key=lambda f: f.palm_size)
        self.locked_side = best_hand.side
        self._last_seen_ns = t_ns
        return best_hand


class GestureEngine:
    """Top-level gesture pipeline dispatcher for Pointer mode."""

    def __init__(
        self,
        config: AileronConfig,
        mapper: CursorMapper | None = None,
        custom_detectors: Sequence[GestureDetector] | None = None,
    ) -> None:
        self.config = config
        if mapper is not None:
            self.mapper = mapper
        else:
            filter_2d = OneEuroFilter2D(
                min_cutoff=config.filters.cursor.min_cutoff,
                beta=config.filters.cursor.beta,
                d_cutoff=config.filters.cursor.d_cutoff,
            )
            self.mapper = CursorMapper(config.pointer, filter_2d=filter_2d)
        self.hand_tracker = PrimaryHandTracker(config.tracking.hand_lost_ms)

        self.pinch_detector = PinchGestureDetector(config.click)
        self.detectors: list[GestureDetector] = [self.pinch_detector]
        if custom_detectors:
            self.detectors.extend(custom_detectors)

    def reset(self) -> None:
        """Reset all internal detectors and state."""
        self.hand_tracker.reset()
        self.mapper.reset()
        for d in self.detectors:
            d.reset()

    def process(
        self,
        hand_frame: HandFrame,
        features: Sequence[HandFeatures],
    ) -> tuple[GestureOutput, tuple[Intent, ...]]:
        """Process one frame of hand features, emitting gesture events and output intents."""
        t_ns = hand_frame.t_capture_ns

        # 1. Primary hand selection
        primary_hand = self.hand_tracker.select(features, t_ns)
        primary_seq: tuple[HandFeatures, ...] = (primary_hand,) if primary_hand is not None else ()

        # 2. Run gesture detectors
        events: list[GestureEvent] = []
        for detector in self.detectors:
            events.extend(detector.update(primary_seq, t_ns))

        # 3. Update cursor freeze based on pinch state
        self.mapper.set_click_freeze(self.pinch_detector.is_cursor_frozen)

        # 4. Map continuous cursor motion
        intents: list[Intent] = []
        cursor_signal: tuple[float, float] | None = None

        if primary_hand is not None:
            cursor_signal = primary_hand.anchor
            move_intent = self.mapper.map_anchor(primary_hand.anchor, t_ns)
            if move_intent is not None:
                intents.append(move_intent)
        else:
            self.mapper.reset()

        # 5. Translate discrete gesture events to intents
        for ev in events:
            translated = self._translate_event_to_intent(ev)
            if translated is not None:
                intents.append(translated)

        # 6. Form GestureOutput and return
        signals = Signals(cursor=cursor_signal)
        gesture_output = GestureOutput(t_ns=t_ns, events=tuple(events), signals=signals)

        return gesture_output, tuple(intents)

    _INTENT_MAP: ClassVar[dict[GestureKind, Intent]] = {
        GestureKind.CLICK_LEFT: Click(button=Button.LEFT, count=1),
        GestureKind.DOUBLE_CLICK: Click(button=Button.LEFT, count=2),
        GestureKind.CLICK_RIGHT: Click(button=Button.RIGHT, count=1),
        GestureKind.CLICK_MIDDLE: Click(button=Button.MIDDLE, count=1),
        GestureKind.DRAG_START: ButtonDown(button=Button.LEFT),
        GestureKind.DRAG_END: ButtonUp(button=Button.LEFT),
    }

    def _translate_event_to_intent(self, ev: GestureEvent) -> Intent | None:
        """Map discrete GestureEvent to an output Intent."""
        return self._INTENT_MAP.get(ev.kind)
