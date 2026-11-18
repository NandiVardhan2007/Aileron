"""Unit tests for two-hand pinch zoom (M3)."""

import numpy as np

from aileron.config import ClickConfig, ZoomConfig
from aileron.gestures.zoom import ZoomDetector, ZoomState
from aileron.interfaces import GestureKind, HandFeatures, Side


def _make_hands(
    x_left: float,
    x_right: float,
    pinch_left: float = 0.20,
    pinch_right: float = 0.20,
    palm_size: float = 0.15,
) -> tuple[HandFeatures, HandFeatures]:
    hl = HandFeatures(
        side=Side.LEFT,
        valid=True,
        palm_size=palm_size,
        anchor=(x_left, 0.5),
        curl={k: 0.8 for k in ("thumb", "index", "middle", "ring", "pinky")},
        pinch={"index": pinch_left, "middle": 0.6, "ring": 0.6, "pinky": 0.6},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        palm_center=(x_left, 0.5),
    )
    hr = HandFeatures(
        side=Side.RIGHT,
        valid=True,
        palm_size=palm_size,
        anchor=(x_right, 0.5),
        curl={k: 0.8 for k in ("thumb", "index", "middle", "ring", "pinky")},
        pinch={"index": pinch_right, "middle": 0.6, "ring": 0.6, "pinky": 0.6},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
        palm_center=(x_right, 0.5),
    )
    return hl, hr


def test_zoom_start_and_steps() -> None:
    """Both hands pinching for >= 80ms emits ZOOM_START.

    Spreading hands emits Zoom(+1), closing hands emits Zoom(-1).
    """
    z_cfg = ZoomConfig(step_fraction=0.06, require_both_pinch_ms=80)
    c_cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35)
    det = ZoomDetector(z_cfg, c_cfg)

    # Frame 1: both hands pinching index at distance = 0.30
    h1 = _make_hands(x_left=0.35, x_right=0.65)
    det.update(h1, t_ns=0)
    assert det.state == ZoomState.PENDING

    # Frame 2 at t = 90ms (elapsed > 80ms) -> ZOOMING, emits ZOOM_START
    evs = det.update(h1, t_ns=90_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.ZOOM_START
    assert det.state == ZoomState.ZOOMING

    # Frame 3: hands spread apart from 0.30 to 0.33 (+10% change > 6% step)
    h_spread = _make_hands(x_left=0.335, x_right=0.665)
    det.update(h_spread, t_ns=110_000_000)
    assert det.zoom_steps_delta >= 1

    # Frame 4: hands move closer from 0.33 to 0.30 (-9% change < -6% step)
    h_close = _make_hands(x_left=0.35, x_right=0.65)
    det.update(h_close, t_ns=130_000_000)
    assert det.zoom_steps_delta <= -1


def test_zoom_release() -> None:
    """Releasing pinch on either hand ends zoom and emits ZOOM_END."""
    z_cfg = ZoomConfig(step_fraction=0.06, require_both_pinch_ms=80)
    c_cfg = ClickConfig(pinch_on=0.25, pinch_off=0.35)
    det = ZoomDetector(z_cfg, c_cfg)

    h_pinch = _make_hands(x_left=0.35, x_right=0.65)
    det.update(h_pinch, t_ns=0)
    det.update(h_pinch, t_ns=90_000_000)
    assert det.state == ZoomState.ZOOMING

    # Left hand releases pinch (ratio 0.40 > 0.35)
    h_rel = _make_hands(x_left=0.35, x_right=0.65, pinch_left=0.40)
    evs = det.update(h_rel, t_ns=120_000_000)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.ZOOM_END
    assert det.state == ZoomState.IDLE
