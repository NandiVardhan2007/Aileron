"""Unit tests for Cockpit mode Yoke profile and Calibration wizard (M5).

Verifies:
- Steering angle calculation, deadzone, expo curve, and range normalization
- Throttle and brake finger-trigger mapping
- Neutral hold (1.0s) and axis ramp-in (200ms)
- Hand-loss neutralization (> 150ms)
- Mode-toggle throttle block rule (SAFE-07)
- Button pinch combinations (gear shift, handbrake, horn)
- Calibration wizard neutral, lock, and trigger steps
"""

import numpy as np

from aileron.calibration.wizard import CalibrationWizard
from aileron.config import CockpitConfig
from aileron.interfaces import (
    Axis,
    Hand,
    HandFeatures,
    Pad,
    PadButton,
    Side,
    Trigger,
)
from aileron.landmarks import Lm
from aileron.modes.manager import ControlMode, ModeManager
from aileron.modes.yoke import (
    YokeProfile,
    shape_steering_axis,
    shape_trigger_axis,
)


def _make_hand(side: Side, mcp_pos: tuple[float, float, float]) -> Hand:
    lm = np.zeros((21, 3), dtype=np.float32)
    world = np.zeros((21, 3), dtype=np.float32)
    lm[int(Lm.MIDDLE_FINGER_MCP)] = mcp_pos
    return Hand(side=side, score=0.95, lm=lm, world=world)


def _make_feat(side: Side, index_curl: float, ring_pinch: float = 1.0) -> HandFeatures:
    return HandFeatures(
        side=side,
        valid=True,
        palm_size=0.15,
        anchor=(0.5, 0.5),
        curl={"index": index_curl},
        pinch={"ring": ring_pinch, "pinky": 1.0},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
        v_gap=0.0,
    )


def test_steering_response_shaping() -> None:
    """Verify deadzone, normalization, and expo curve on steering angle."""
    dz = 3.0
    max_deg = 45.0
    expo = 0.35

    # 1. Within deadzone -> 0.0
    assert shape_steering_axis(2.0, dz, max_deg, expo) == 0.0
    assert shape_steering_axis(-2.5, dz, max_deg, expo) == 0.0

    # 2. At maximum angle -> +1.0 or -1.0
    assert shape_steering_axis(45.0, dz, max_deg, expo) == 1.0
    assert shape_steering_axis(-45.0, dz, max_deg, expo) == -1.0

    # 3. Intermediate angle: progressive curve
    mid = shape_steering_axis(24.0, dz, max_deg, expo)
    assert 0.0 < mid < 1.0


def test_trigger_response_shaping() -> None:
    """Verify trigger deadzone and extension range scaling."""
    ext_min = 0.30
    ext_max = 0.85
    dz = 0.05
    curve = 1.0

    # Fully curled -> 0.0
    assert shape_trigger_axis(0.20, ext_min, ext_max, dz, curve) == 0.0
    # Inside deadzone
    assert shape_trigger_axis(0.31, ext_min, ext_max, dz, curve) == 0.0
    # Fully extended -> 1.0
    assert shape_trigger_axis(0.85, ext_min, ext_max, dz, curve) == 1.0
    # Mid-range
    mid = shape_trigger_axis(0.60, ext_min, ext_max, dz, curve)
    assert 0.4 < mid < 0.7


def test_neutral_hold_and_ramp_in() -> None:
    """Yoke axes remain 0 during neutral hold, then ramp in over ramp_in_ms."""
    c_cfg = CockpitConfig(neutral_hold_ms=1000, ramp_in_ms=200)
    yoke = YokeProfile(cockpit_cfg=c_cfg)

    # Level hands at t = 0 (relaxed neutral triggers)
    lh = _make_hand(Side.LEFT, (0.3, 0.5, 0.0))
    rh = _make_hand(Side.RIGHT, (0.7, 0.5, 0.0))
    lf = _make_feat(Side.LEFT, index_curl=0.1)
    rf_rest = _make_feat(Side.RIGHT, index_curl=0.1)
    rf_active = _make_feat(Side.RIGHT, index_curl=0.8)  # throttle extended

    # Tick 1: t = 0 -> not live
    intents1 = yoke.process([lh, rh], [lf, rf_rest], t_ns=0)
    assert not yoke.is_axes_live
    assert all(getattr(i, "value", 0.0) == 0.0 for i in intents1)

    # Tick 2: t = 500ms -> still not live (needs 1000ms)
    yoke.process([lh, rh], [lf, rf_rest], t_ns=500_000_000)
    assert not yoke.is_axes_live

    # Tick 3: t = 1050ms -> neutral hold completes! Axes go live
    yoke.process([lh, rh], [lf, rf_rest], t_ns=1_050_000_000)
    assert yoke.is_axes_live

    # Tick 4: t = 1250ms -> throttle applied; ramp-in completes (200ms elapsed since live)
    intents4 = yoke.process([lh, rh], [lf, rf_active], t_ns=1_250_000_000)
    tr = next((i for i in intents4 if isinstance(i, Trigger) and i.name == "rt"), None)
    assert tr is not None
    assert tr.value > 0.5


def test_hand_loss_neutralization() -> None:
    """Missing hand > 150ms neutralizes steering and throttle."""
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0, on_loss="neutral")
    yoke = YokeProfile(cockpit_cfg=c_cfg)

    # Active hands - hold neutral first to go live
    lh = _make_hand(Side.LEFT, (0.3, 0.5, 0.0))
    rh = _make_hand(Side.RIGHT, (0.7, 0.5, 0.0))
    lf = _make_feat(Side.LEFT, 0.1)
    rf = _make_feat(Side.RIGHT, 0.1)

    yoke.process([lh, rh], [lf, rf], t_ns=0)
    yoke.process([lh, rh], [lf, rf], t_ns=120_000_000)
    assert yoke.is_axes_live

    # Left hand vanishes at t = 160ms (elapsed 40ms <= 150ms) -> holds steer
    intents_hold = yoke.process([rh], [rf], t_ns=160_000_000)
    ax = next((i for i in intents_hold if isinstance(i, Axis)), None)
    assert ax is not None

    # Missing at t = 350ms (elapsed 230ms > 150ms) -> neutralized!
    intents_neutral = yoke.process([rh], [rf], t_ns=350_000_000)
    assert not yoke.is_axes_live
    for i in intents_neutral:
        if isinstance(i, Axis | Trigger):
            assert i.value == 0.0


def test_mode_toggle_block_at_active_throttle() -> None:
    """SAFE-07: Shaka mode toggle is blocked when Cockpit throttle > 0.3."""
    c_cfg = CockpitConfig(mode_toggle_block_throttle=0.3)
    mm = ModeManager(config=c_cfg, initial_mode=ControlMode.COCKPIT)

    # Attempt toggle with high throttle (0.6 > 0.3)
    mode, releases = mm.toggle_mode(current_throttle=0.6)
    assert mode == ControlMode.COCKPIT  # blocked!
    assert len(releases) == 0

    # Attempt toggle with low throttle (0.1 <= 0.3)
    mode, releases = mm.toggle_mode(current_throttle=0.1)
    assert mode == ControlMode.POINTER  # permitted!
    assert len(releases) > 0


def test_button_pinch_combos() -> None:
    """Pinch combinations trigger gear shifts and cockpit buttons."""
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0)
    yoke = YokeProfile(cockpit_cfg=c_cfg)
    yoke._axes_live = True

    lh = _make_hand(Side.LEFT, (0.3, 0.5, 0.0))
    rh = _make_hand(Side.RIGHT, (0.7, 0.5, 0.0))

    # Right hand pinching ring (gear up -> RB)
    lf = _make_feat(Side.LEFT, index_curl=0.2, ring_pinch=1.0)
    rf = _make_feat(Side.RIGHT, index_curl=0.2, ring_pinch=0.15)

    intents = yoke.process([lh, rh], [lf, rf], t_ns=100_000_000)
    pad = next((i for i in intents if isinstance(i, Pad) and i.button == PadButton.RB), None)
    assert pad is not None
    assert pad.down


def test_calibration_wizard_steps() -> None:
    """Verify calibration wizard computes neutral angle, lock angle, and trigger bounds."""
    wiz = CalibrationWizard()

    # 1. Neutral calibration with horizontal hands
    lh = _make_hand(Side.LEFT, (0.3, 0.5, 0.0))
    rh = _make_hand(Side.RIGHT, (0.7, 0.5, 0.0))
    neutral = wiz.calibrate_neutral([(lh, rh), (lh, rh)])
    assert abs(neutral) < 2.0

    # 2. Lock calibration with tilted hands
    lh_tilted = _make_hand(Side.LEFT, (0.3, 0.6, 0.0))
    rh_tilted = _make_hand(Side.RIGHT, (0.7, 0.4, 0.0))
    lock_deg = wiz.calibrate_lock([(lh_tilted, rh_tilted)], [(lh_tilted, rh_tilted)])
    assert lock_deg > 15.0

    # 3. Trigger calibration
    rest = [_make_feat(Side.RIGHT, index_curl=0.25)]
    ext = [_make_feat(Side.RIGHT, index_curl=0.88)]
    t_min, t_max = wiz.calibrate_triggers(rest, ext, side=Side.RIGHT)
    assert t_min < 0.35
    assert t_max > 0.80
