"""Unit tests for V-sign joystick scrolling (M3)."""

import numpy as np

from aileron.config import FingersConfig, ScrollConfig
from aileron.gestures.scroll import ScrollDetector, ScrollState
from aileron.interfaces import GestureKind, HandFeatures, Side


def _make_v_features(
    anchor: tuple[float, float] = (0.5, 0.5),
    idx_ext: float = 0.85,
    mid_ext: float = 0.85,
    rng_ext: float = 0.15,
    pnk_ext: float = 0.15,
    gap: float = 0.35,
    palm_size: float = 0.15,
) -> tuple[HandFeatures]:
    hf = HandFeatures(
        side=Side.RIGHT,
        valid=True,
        palm_size=palm_size,
        anchor=anchor,
        curl={"thumb": 0.2, "index": idx_ext, "middle": mid_ext, "ring": rng_ext, "pinky": pnk_ext},
        pinch={"index": 0.7, "middle": 0.7, "ring": 0.8, "pinky": 0.8},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
        v_gap=gap,
    )
    return (hf,)


def test_scroll_vsign_detection_and_dwell() -> None:
    """V-sign held >= hold_ms (120ms) transitions to SCROLLING and emits SCROLL_START."""
    s_cfg = ScrollConfig(deadzone=0.15, gain=40.0, power=1.5, max_lines_per_s=60.0, hold_ms=120)
    f_cfg = FingersConfig(ext_on=0.75, ext_off=0.35)
    det = ScrollDetector(s_cfg, f_cfg)

    # 1. Idle initially
    assert det.state == ScrollState.IDLE
    assert not det.is_cursor_frozen

    # 2. V-sign pose starts at t = 100ms
    evs1 = det.update(_make_v_features(anchor=(0.5, 0.5)), t_ns=100_000_000)
    assert len(evs1) == 0
    assert det.state == ScrollState.PENDING
    assert det.is_cursor_frozen

    # 3. Intermediate frame at t = 180ms (elapsed 80ms < 120ms)
    evs2 = det.update(_make_v_features(anchor=(0.5, 0.5)), t_ns=180_000_000)
    assert len(evs2) == 0
    assert det.state == ScrollState.PENDING

    # 4. Reaches 120ms at t = 220ms (elapsed 120ms) -> SCROLLING
    evs3 = det.update(_make_v_features(anchor=(0.5, 0.5)), t_ns=220_000_000)
    assert len(evs3) == 1
    assert evs3[0].kind == GestureKind.SCROLL_START
    assert det.state == ScrollState.SCROLLING
    assert det.is_cursor_frozen


def test_scroll_joystick_rate_and_deadzone() -> None:
    """Displacement beyond deadzone computes power curve rate; within deadzone produces 0."""
    s_cfg = ScrollConfig(deadzone=0.15, gain=40.0, power=1.5, max_lines_per_s=60.0, hold_ms=100)
    f_cfg = FingersConfig()
    det = ScrollDetector(s_cfg, f_cfg)

    # Enter scrolling with anchor at (0.5, 0.5), palm_size = 0.10
    det.update(_make_v_features(anchor=(0.5, 0.5), palm_size=0.10), t_ns=0)
    det.update(_make_v_features(anchor=(0.5, 0.5), palm_size=0.10), t_ns=120_000_000)
    assert det.state == ScrollState.SCROLLING

    # Move anchor to (0.5, 0.49): dy_image = -0.01 -> dy_palm = +0.10 (within deadzone 0.15)
    det.update(_make_v_features(anchor=(0.5, 0.49), palm_size=0.10), t_ns=140_000_000)
    assert det.scroll_rate[1] == 0.0

    # Move anchor to (0.5, 0.46): dy_image = -0.04 -> dy_palm = +0.40 (excess 0.25)
    # excess = 0.25, rate = (0.25^1.5) * 40 = 0.125 * 40 = 5.0 lines/s
    det.update(_make_v_features(anchor=(0.5, 0.46), palm_size=0.10), t_ns=160_000_000)
    assert det.scroll_rate[1] > 0.0
    assert abs(det.scroll_rate[1] - 5.0) < 0.1

    # Hand moves back to initial anchor (0.5, 0.5) -> rate goes back to 0.0
    det.update(_make_v_features(anchor=(0.5, 0.5), palm_size=0.10), t_ns=180_000_000)
    assert det.scroll_rate[1] == 0.0


def test_scroll_end_on_pose_break_or_hand_lost() -> None:
    """Breaking V-sign pose or losing hand emits SCROLL_END."""
    s_cfg = ScrollConfig(hold_ms=100)
    f_cfg = FingersConfig()
    det = ScrollDetector(s_cfg, f_cfg)

    # Enter scrolling
    det.update(_make_v_features(), t_ns=0)
    det.update(_make_v_features(), t_ns=120_000_000)
    assert det.state == ScrollState.SCROLLING

    # Pose breaks: fingers curled (idx_ext = 0.2)
    evs = det.update(_make_v_features(idx_ext=0.2), t_ns=150_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.SCROLL_END
    assert det.state == ScrollState.IDLE
    assert not det.is_cursor_frozen
