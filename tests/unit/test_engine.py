"""Unit tests for GestureEngine and PrimaryHandTracker."""

from collections.abc import Sequence

import numpy as np

from aileron.config import load_config
from aileron.gestures.engine import GestureEngine, PrimaryHandTracker
from aileron.interfaces import (
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    GestureEvent,
    GestureKind,
    Hand,
    HandFeatures,
    HandFrame,
    MoveTo,
    Side,
)
from aileron.mapping.cursor import CursorMapper


class DummyCustomDetector:
    """Dummy detector to verify custom plugin / extension point integration."""

    name: str = "dummy"

    def __init__(self) -> None:
        self.reset_called = False

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        return ()

    def reset(self) -> None:
        self.reset_called = True


def _make_hand(side: Side = Side.RIGHT) -> Hand:
    lm = np.zeros((21, 3), dtype=np.float32)
    world = np.zeros((21, 3), dtype=np.float32)
    return Hand(side=side, score=0.95, lm=lm, world=world)


def _make_feat(
    side: Side = Side.RIGHT, valid: bool = True, palm_size: float = 0.15
) -> HandFeatures:
    return HandFeatures(
        side=side,
        valid=valid,
        palm_size=palm_size,
        anchor=(0.5, 0.5),
        curl={k: 0.8 for k in ("thumb", "index", "middle", "ring", "pinky")},
        pinch={"index": 0.5, "middle": 0.6, "ring": 0.6, "pinky": 0.6},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
    )


def test_primary_hand_tracker_sticky_and_timeout() -> None:
    """PrimaryHandTracker locks to first engaged hand and unlocks on timeout."""
    tracker = PrimaryHandTracker(hand_lost_ms=150, engage_ms=300)
    assert tracker.locked_side is None

    # Empty frame
    h, _evs = tracker.select((), t_ns=0)
    assert h is None

    # Two hands appear: Left (palm=0.12) and Right (palm=0.18)
    h_left = _make_feat(Side.LEFT, palm_size=0.12)
    h_right = _make_feat(Side.RIGHT, palm_size=0.18)

    selected, _evs = tracker.select((h_left, h_right), t_ns=100_000_000)
    assert selected is not None
    assert selected.side == Side.RIGHT
    assert tracker.locked_side == Side.RIGHT

    # Next frame: Left palm grows larger (0.22), but Right is still locked!
    h_left_larger = _make_feat(Side.LEFT, palm_size=0.22)
    selected2, _evs = tracker.select((h_left_larger, h_right), t_ns=120_000_000)
    assert selected2 is not None
    assert selected2.side == Side.RIGHT

    # Right hand lost at t = 200ms, only left hand present
    # Elapsed since last seen (120ms) is 80ms < 150ms -> still locked to Right, returns None
    selected_grace, _evs = tracker.select((h_left_larger,), t_ns=200_000_000)
    assert selected_grace is None

    # At t = 300ms (elapsed 180ms > 150ms) -> timeout unlocks, Left hand can now engage
    selected_after_timeout, _evs = tracker.select((h_left_larger,), t_ns=300_000_000)
    assert selected_after_timeout is not None
    assert selected_after_timeout.side == Side.LEFT
    assert tracker.locked_side == Side.LEFT

    # Explicit reset
    tracker.reset()
    assert tracker.locked_side is None


def test_gesture_engine_intents_and_lifecycle() -> None:
    """Verify GestureEngine translates events to intents, passes custom detectors, and resets."""
    config = load_config()
    custom_det = DummyCustomDetector()
    mapper = CursorMapper(config.pointer)
    engine = GestureEngine(config, mapper=mapper, custom_detectors=[custom_det])

    # Process empty frame
    empty_frame = HandFrame(t_capture_ns=0, t_infer_done_ns=0, seq=0, hands=())
    out, intents = engine.process(empty_frame, ())
    assert len(out.events) == 0
    assert len(intents) == 0
    assert out.signals.cursor is None

    # Process active frame with hand (advance past engage_ms=300ms)
    hand = _make_hand(Side.RIGHT)
    feat = _make_feat(Side.RIGHT, palm_size=0.15)
    # First frame at t = 100ms: hand detected, engage dwell running
    frame1 = HandFrame(t_capture_ns=100_000_000, t_infer_done_ns=100_000_000, seq=1, hands=(hand,))
    engine.process(frame1, (feat,))

    # Second frame at t = 450ms (> 300ms): hand engaged, MoveTo emitted
    frame2 = HandFrame(t_capture_ns=450_000_000, t_infer_done_ns=450_000_000, seq=2, hands=(hand,))
    out2, intents2 = engine.process(frame2, (feat,))
    assert out2.signals.cursor == (0.5, 0.5)
    assert any(isinstance(it, MoveTo) for it in intents2)

    # Test event translation helpers
    ev_left = GestureEvent(kind=GestureKind.CLICK_LEFT, t_ns=0, side=Side.RIGHT)
    ev_dbl = GestureEvent(kind=GestureKind.DOUBLE_CLICK, t_ns=0, side=Side.RIGHT)
    ev_right = GestureEvent(kind=GestureKind.CLICK_RIGHT, t_ns=0, side=Side.RIGHT)
    ev_mid = GestureEvent(kind=GestureKind.CLICK_MIDDLE, t_ns=0, side=Side.RIGHT)
    ev_drag_start = GestureEvent(kind=GestureKind.DRAG_START, t_ns=0, side=Side.RIGHT)
    ev_drag_end = GestureEvent(kind=GestureKind.DRAG_END, t_ns=0, side=Side.RIGHT)
    ev_unknown = GestureEvent(kind=GestureKind.ENGAGED, t_ns=0, side=Side.RIGHT)

    assert engine._translate_event_to_intent(ev_left) == Click(button=Button.LEFT, count=1)
    assert engine._translate_event_to_intent(ev_dbl) == Click(button=Button.LEFT, count=2)
    assert engine._translate_event_to_intent(ev_right) == Click(button=Button.RIGHT, count=1)
    assert engine._translate_event_to_intent(ev_mid) == Click(button=Button.MIDDLE, count=1)
    assert engine._translate_event_to_intent(ev_drag_start) == ButtonDown(button=Button.LEFT)
    assert engine._translate_event_to_intent(ev_drag_end) == ButtonUp(button=Button.LEFT)
    assert engine._translate_event_to_intent(ev_unknown) is None

    # Reset
    engine.reset()
    assert custom_det.reset_called
