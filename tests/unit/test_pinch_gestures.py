"""Unit tests for pinch gesture FSMs: clicks, drags, double click, right/middle click."""

import numpy as np

from aileron.config import ClickConfig
from aileron.gestures.pinch import (
    PinchGestureDetector,
    PinchLeftDetector,
    PinchMiddleDetector,
    PinchRightDetector,
    PinchState,
)
from aileron.interfaces import GestureKind, HandFeatures, Side


def _make_features(
    pinch: dict[str, float],
    side: Side = Side.RIGHT,
    valid: bool = True,
    palm_size: float = 0.15,
) -> tuple[HandFeatures]:
    """Helper to create minimal HandFeatures for testing pinch detectors."""
    hf = HandFeatures(
        side=side,
        valid=valid,
        palm_size=palm_size,
        anchor=(0.5, 0.5),
        curl={k: 0.8 for k in ("thumb", "index", "middle", "ring", "pinky")},
        pinch=pinch,
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
    )
    return (hf,)


def test_left_click_tap_positive() -> None:
    """A clean pinch tap between min_pinch_ms (40ms) and tap_ms (300ms) emits CLICK_LEFT."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    det = PinchLeftDetector(cfg)

    # 1. Start open
    evs = det.update(_make_features({"index": 0.5, "middle": 0.6}), t_ns=0)
    assert len(evs) == 0
    assert det.state == PinchState.OPEN
    assert not det.is_cursor_frozen

    # 2. Pinch down at t = 100ms
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    assert len(evs) == 0
    assert det.state == PinchState.PINCH_PENDING
    assert det.is_cursor_frozen

    # 3. Hold at t = 150ms (elapsed 50ms, > 40ms)
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=150_000_000)
    assert len(evs) == 0
    assert det.state == PinchState.PINCH_PENDING

    # 4. Release at t = 180ms (> pinch_off 0.35)
    evs = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=180_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLICK_LEFT
    assert det.state == PinchState.OPEN
    assert not det.is_cursor_frozen


def test_noise_spike_discarded() -> None:
    """A pinch duration shorter than min_pinch_ms is discarded as noise."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    det = PinchLeftDetector(cfg)

    # Pinch down at t = 100ms
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    assert det.state == PinchState.PINCH_PENDING

    # Release at t = 120ms (elapsed only 20ms < min_pinch_ms=40ms)
    evs = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=120_000_000)
    assert len(evs) == 0
    assert det.state == PinchState.OPEN
    assert not det.is_cursor_frozen


def test_drag_start_and_drag_end() -> None:
    """A pinch held >= tap_ms enters DRAGGING and emits DRAG_START, then DRAG_END."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    det = PinchLeftDetector(cfg)

    # Pinch down at t = 100ms
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    assert det.is_cursor_frozen

    # Intermediate frame at 250ms (elapsed 150ms < 300ms)
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=250_000_000)
    assert len(evs) == 0
    assert det.state == PinchState.PINCH_PENDING
    assert det.is_cursor_frozen

    # Reaches 300ms hold at t = 400ms (elapsed 300ms)
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=400_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.DRAG_START
    assert det.state == PinchState.DRAGGING
    # Cursor is un-frozen during drag so cursor can follow hand!
    assert not det.is_cursor_frozen

    # Drag continues at t = 600ms
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=600_000_000)
    assert len(evs) == 0

    # Release at t = 700ms
    evs = det.update(_make_features({"index": 0.42, "middle": 0.6}), t_ns=700_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.DRAG_END
    assert det.state == PinchState.OPEN


def test_drag_hand_lost_failsafe() -> None:
    """SAFE-02: If hand is lost while dragging, DRAG_END must be emitted immediately."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    det = PinchLeftDetector(cfg)

    # Start pinch at t = 0, drag at t = 300ms
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=0)
    evs = det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=300_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.DRAG_START
    assert det.state == PinchState.DRAGGING

    # Hand disappears at t = 350ms
    evs = det.update((), t_ns=350_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.DRAG_END
    assert det.state == PinchState.OPEN


def test_double_click_detection() -> None:
    """Two taps within dbl_ms emit DOUBLE_CLICK on the second tap."""
    cfg = ClickConfig(
        pinch_on=0.25,
        pinch_off=0.35,
        min_pinch_ms=40,
        tap_ms=300,
        dbl_ms=350,
        max_clicks_per_s=20,
    )
    det = PinchLeftDetector(cfg)

    # Tap 1: 100ms -> 180ms (80ms pinch)
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    evs1 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=180_000_000)
    assert len(evs1) == 1
    assert evs1[0].kind == GestureKind.CLICK_LEFT

    # Gap of 100ms: t = 280ms
    det.update(_make_features({"index": 0.45, "middle": 0.6}), t_ns=280_000_000)

    # Tap 2: 300ms -> 380ms (interval from tap1 release is 200ms < 350ms)
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=300_000_000)
    evs2 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=380_000_000)
    assert len(evs2) == 1
    assert evs2[0].kind == GestureKind.DOUBLE_CLICK


def test_slow_taps_emit_single_clicks() -> None:
    """Two taps separated by more than dbl_ms emit two single clicks."""
    cfg = ClickConfig(
        pinch_on=0.25,
        pinch_off=0.35,
        min_pinch_ms=40,
        tap_ms=300,
        dbl_ms=350,
        max_clicks_per_s=20,
    )
    det = PinchLeftDetector(cfg)

    # Tap 1: 100ms -> 180ms
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    evs1 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=180_000_000)
    assert len(evs1) == 1
    assert evs1[0].kind == GestureKind.CLICK_LEFT

    # Tap 2 happens at 600ms (interval 420ms > 350ms)
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=600_000_000)
    evs2 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=680_000_000)
    assert len(evs2) == 1
    assert evs2[0].kind == GestureKind.CLICK_LEFT


def test_hysteresis_flicker_rejection() -> None:
    """TEST-01: Pinch oscillating between on and off thresholds remains pending."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    det = PinchLeftDetector(cfg)

    # Activate pinch at 0.22 (< 0.25)
    det.update(_make_features({"index": 0.22, "middle": 0.6}), t_ns=0)
    assert det.state == PinchState.PINCH_PENDING

    # Oscillate in hysteresis band: 0.28, 0.32, 0.26, 0.33
    for ratio, t_ms in [(0.28, 20), (0.32, 40), (0.26, 60), (0.33, 80)]:
        evs = det.update(_make_features({"index": ratio, "middle": 0.6}), t_ns=t_ms * 1_000_000)
        assert len(evs) == 0
        assert det.state == PinchState.PINCH_PENDING, f"Flickered at ratio={ratio}"

    # Only when crossing pinch_off (0.36 > 0.35) does it release
    evs = det.update(_make_features({"index": 0.36, "middle": 0.6}), t_ns=100_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLICK_LEFT
    assert det.state == PinchState.OPEN


def test_conflict_margin_index_vs_middle() -> None:
    """Conflict margin: if middle finger is closer than margin, left pinch does NOT trigger."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, margin=0.08)
    det = PinchLeftDetector(cfg)

    # Index is 0.24, but middle is 0.23 (difference is -0.01 < 0.08)
    evs = det.update(_make_features({"index": 0.24, "middle": 0.23}), t_ns=100_000_000)
    assert len(evs) == 0
    assert det.state == PinchState.OPEN, "Conflict margin failed to block ambiguous pinch"


def test_right_click_tap() -> None:
    """Middle finger pinch tap emits CLICK_RIGHT."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300, margin=0.08)
    det = PinchRightDetector(cfg)

    # Open hand
    det.update(_make_features({"index": 0.6, "middle": 0.6}), t_ns=0)
    assert det.state == PinchState.OPEN

    # Middle finger pinches down (0.20 < 0.25, index is 0.60 > 0.35)
    det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=100_000_000)
    assert det.state == PinchState.PINCH_PENDING
    assert det.is_cursor_frozen

    # Hold for 80ms, then release at t = 180ms
    evs = det.update(_make_features({"index": 0.6, "middle": 0.40}), t_ns=180_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLICK_RIGHT
    assert det.state == PinchState.OPEN
    assert not det.is_cursor_frozen


def test_middle_click_tap() -> None:
    """Ring finger pinch tap emits CLICK_MIDDLE."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300, margin=0.08)
    det = PinchMiddleDetector(cfg)

    # Open hand
    det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.6, "pinky": 0.6}),
        t_ns=0,
    )

    # Ring finger pinches down (0.20 < 0.25, index and middle are > 0.35)
    det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=100_000_000,
    )
    assert det.state == PinchState.PINCH_PENDING

    # Release at t = 180ms
    evs = det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.40, "pinky": 0.6}),
        t_ns=180_000_000,
    )
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLICK_MIDDLE
    assert det.state == PinchState.OPEN


def test_rate_limiting_clicks() -> None:
    """Clicks faster than max_clicks_per_s are suppressed."""
    cfg = ClickConfig(
        pinch_on=0.25,
        pinch_off=0.35,
        min_pinch_ms=20,
        tap_ms=100,
        max_clicks_per_s=4,  # min interval = 250ms
    )
    det = PinchLeftDetector(cfg)

    # First click at t = 100ms -> releases at t = 140ms
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    evs1 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=140_000_000)
    assert len(evs1) == 1
    assert evs1[0].kind == GestureKind.CLICK_LEFT

    # Immediate second click at t = 160ms -> releases at t = 200ms (elapsed 60ms < 250ms)
    det.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=160_000_000)
    evs2 = det.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=200_000_000)
    assert len(evs2) == 0, "Rate limit should have suppressed this click"


def test_pinch_right_and_middle_edge_cases() -> None:
    """Verify hold timeout, rate limits, empty frames, and resets on right and middle detectors."""
    cfg = ClickConfig(
        pinch_on=0.25,
        pinch_off=0.35,
        min_pinch_ms=20,
        tap_ms=100,
        max_clicks_per_s=4,  # 250ms min interval
        margin=0.08,
    )
    r_det = PinchRightDetector(cfg)
    m_det = PinchMiddleDetector(cfg)

    # 1. Right detector hold timeout
    r_det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=100_000_000)
    assert r_det.state == PinchState.PINCH_PENDING
    # Elapsed 150ms > tap_ms (100ms) -> cancelled
    r_det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=250_000_000)
    assert r_det.state == PinchState.OPEN
    # Release after cancel -> no event
    assert len(r_det.update(_make_features({"index": 0.6, "middle": 0.50}), t_ns=260_000_000)) == 0

    # 2. Middle detector hold timeout
    m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=100_000_000,
    )
    assert m_det.state == PinchState.PINCH_PENDING
    m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=250_000_000,
    )
    assert m_det.state == PinchState.OPEN

    # 3. Rate limiting on right detector
    r_det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=300_000_000)
    evs1 = r_det.update(_make_features({"index": 0.6, "middle": 0.40}), t_ns=340_000_000)
    assert len(evs1) == 1
    # Immediate second right tap at 360ms -> release at 390ms (< 250ms interval)
    r_det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=360_000_000)
    evs2 = r_det.update(_make_features({"index": 0.6, "middle": 0.40}), t_ns=390_000_000)
    assert len(evs2) == 0

    # 4. Rate limiting on middle detector
    m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=300_000_000,
    )
    evs_m1 = m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.40, "pinky": 0.6}),
        t_ns=340_000_000,
    )
    assert len(evs_m1) == 1
    m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=360_000_000,
    )
    evs_m2 = m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.40, "pinky": 0.6}),
        t_ns=390_000_000,
    )
    assert len(evs_m2) == 0

    # 5. Empty/invalid frames reset detectors cleanly
    r_det.update(_make_features({"index": 0.6, "middle": 0.20}), t_ns=700_000_000)
    assert r_det.state == PinchState.PINCH_PENDING
    r_det.update((), t_ns=710_000_000)
    assert r_det.state == PinchState.OPEN

    m_det.update(
        _make_features({"index": 0.6, "middle": 0.6, "ring": 0.20, "pinky": 0.6}),
        t_ns=700_000_000,
    )
    assert m_det.state == PinchState.PINCH_PENDING
    m_det.update((), t_ns=710_000_000)
    assert m_det.state == PinchState.OPEN

    # 6. Explicit resets
    r_det.reset()
    m_det.reset()
    assert r_det.state == PinchState.OPEN
    assert m_det.state == PinchState.OPEN


def test_unified_pinch_gesture_detector() -> None:
    """Verify PinchGestureDetector coordinates all pinch detectors and reset."""
    cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35, min_pinch_ms=40, tap_ms=300)
    detector = PinchGestureDetector(cfg)
    assert detector.name == "pinch"
    assert not detector.is_cursor_frozen

    # Start pinch left
    detector.update(_make_features({"index": 0.20, "middle": 0.6}), t_ns=100_000_000)
    assert detector.is_cursor_frozen

    # Release pinch left -> CLICK_LEFT
    evs = detector.update(_make_features({"index": 0.40, "middle": 0.6}), t_ns=180_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLICK_LEFT
    assert not detector.is_cursor_frozen

    # Reset
    detector.reset()
    assert not detector.is_cursor_frozen
