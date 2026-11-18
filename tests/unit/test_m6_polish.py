"""Unit tests for M6 Handlebar profile, profile migrations, onboarding, and accessibility.

Verifies:
- Handlebar single-hand roll steering and throttle mapping
- Profile import, export, and schema migration (v0 -> v1)
- Interactive onboarding steps progression and checks
- Accessibility stability mode overrides and DwellClick detector
- HUD compact and full rendering
"""

from pathlib import Path

import numpy as np

from aileron.accessibility import AccessibilityManager, DwellClickDetector
from aileron.config import AileronConfig, CockpitConfig, CockpitHandlebarConfig
from aileron.interfaces import (
    Axis,
    Button,
    Click,
    Hand,
    HandFeatures,
    Side,
    Trigger,
)
from aileron.landmarks import Lm
from aileron.modes.handlebar import HandlebarProfile
from aileron.onboarding import OnboardingFlow, OnboardingStep
from aileron.profiles import apply_migrations, export_profile, import_profile
from aileron.ui.hud import HudManager, HudMode


def _make_hand_with_roll(side: Side, roll_deg: float) -> Hand:
    lm = np.zeros((21, 3), dtype=np.float32)
    world = np.zeros((21, 3), dtype=np.float32)

    # Wrist L0 at origin
    world[int(Lm.WRIST)] = [0.0, 0.0, 0.0]
    # Rotate vector L0 -> L9 by roll_deg
    rad = np.radians(roll_deg)
    length = 0.10
    world[int(Lm.MIDDLE_FINGER_MCP)] = [length * np.sin(rad), -length * np.cos(rad), 0.0]
    return Hand(side=side, score=0.95, lm=lm, world=world)


def _make_features(side: Side, index_curl: float = 0.5, pinch_index: float = 0.3) -> HandFeatures:
    return HandFeatures(
        side=side,
        valid=True,
        palm_size=0.15,
        anchor=(0.5, 0.5),
        curl={"index": index_curl},
        pinch={"index": pinch_index, "ring": 1.0, "pinky": 1.0},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
        v_gap=0.0,
    )


def test_handlebar_roll_steering() -> None:
    """Handlebar profile maps single-hand wrist lean to steering axis."""
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0)
    hb_cfg = CockpitHandlebarConfig(steer_max_deg=35.0, steer_deadzone_deg=3.0)
    hb = HandlebarProfile(cockpit_cfg=c_cfg, handlebar_cfg=hb_cfg)
    hb._axes_live = True

    # 1. Lean right +20 degrees (clockwise) -> positive steer axis
    h_right_tilt = _make_hand_with_roll(Side.RIGHT, roll_deg=20.0)
    f_right = _make_features(Side.RIGHT)
    intents = hb.process([h_right_tilt], [f_right], t_ns=100_000_000)

    steer = next((i for i in intents if isinstance(i, Axis) and i.name == "lx"), None)
    assert steer is not None
    assert steer.value > 0.3

    # 2. Lean left -20 degrees -> negative steer axis (settle filter)
    h_left_tilt = _make_hand_with_roll(Side.RIGHT, roll_deg=-20.0)
    hb.process([h_left_tilt], [f_right], t_ns=200_000_000)
    intents_left = hb.process([h_left_tilt], [f_right], t_ns=300_000_000)
    steer_left = next((i for i in intents_left if isinstance(i, Axis) and i.name == "lx"), None)
    assert steer_left is not None
    assert steer_left.value < -0.3


def test_handlebar_throttle_sources() -> None:
    """Handlebar supports thumb curl and index finger extension throttle sources."""
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0)
    # Index throttle
    hb_cfg = CockpitHandlebarConfig(throttle_source="index")
    hb = HandlebarProfile(cockpit_cfg=c_cfg, handlebar_cfg=hb_cfg)
    hb._axes_live = True

    h = _make_hand_with_roll(Side.RIGHT, roll_deg=0.0)
    f_ext = _make_features(Side.RIGHT, index_curl=0.85)  # extended
    intents = hb.process([h], [f_ext], t_ns=100_000_000)

    tr = next((i for i in intents if isinstance(i, Trigger) and i.name == "rt"), None)
    assert tr is not None
    assert tr.value > 0.7


def test_profile_export_and_import(tmp_path: Path) -> None:
    """Profile export writes TOML with schema_version, and import reloads it."""
    cfg = AileronConfig()
    cfg.pointer.gamma = 1.4
    dest = tmp_path / "test_profile.toml"

    out_path = export_profile(cfg, dest, calibration_data={"neutral_deg": -1.2})
    assert out_path.exists()

    imported = import_profile(out_path)
    assert imported["schema_version"] == 1
    assert imported["pointer"]["gamma"] == 1.4
    assert imported["calibration"]["neutral_deg"] == -1.2


def test_profile_schema_migration() -> None:
    """Legacy v0 profile without schema_version is automatically upgraded to v1."""
    legacy_v0 = {
        "pointer": {"gamma": 1.2},
        "yoke": {"steer_max_deg": 50.0},
    }
    migrated = apply_migrations(legacy_v0)
    assert migrated["schema_version"] == 1
    assert "cockpit" in migrated
    assert migrated["cockpit"]["yoke"]["steer_max_deg"] == 50.0


def test_onboarding_flow_progression() -> None:
    """Onboarding verifies camera, handedness check, practice, and safety briefing."""
    flow = OnboardingFlow()
    assert flow.state.current_step == OnboardingStep.WELCOME

    # Camera check
    assert flow.verify_camera(fps=30.0, width=1280, height=720)
    flow.advance_to(OnboardingStep.CAMERA_CHECK)

    # Handedness check
    h_right = _make_hand_with_roll(Side.RIGHT, 0.0)
    assert flow.verify_handedness([h_right], Side.RIGHT)
    flow.advance_to(OnboardingStep.HANDEDNESS_CHECK)

    # Practice pinch
    assert flow.record_practice_pinch(0.18)
    flow.advance_to(OnboardingStep.PRACTICE_PINCH)

    # Safety briefing
    f_fist = HandFeatures(
        side=Side.RIGHT,
        valid=True,
        palm_size=0.15,
        anchor=(0.5, 0.5),
        curl={"thumb": 0.1, "index": 0.1, "middle": 0.1, "ring": 0.1, "pinky": 0.1},
        pinch={"ring": 1.0, "pinky": 1.0},
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, -1.0], dtype=np.float32),
        palm_center=(0.5, 0.5),
        v_gap=0.0,
    )
    assert flow.record_safety_clutch(f_fist)
    flow.acknowledge_kill_switch()
    flow.advance_to(OnboardingStep.COMPLETE)

    assert flow.state.completed


def test_dwell_click_detection() -> None:
    """Hovering stationary within radius emits Click(LEFT) after dwell_ms."""
    det = DwellClickDetector(dwell_ms=400, radius_px=10.0)

    # Frame 1: anchor established at (500, 500)
    res1 = det.update((500, 500), t_ns=0)
    assert len(res1) == 0

    # Frame 2: small jitter (502, 501) at t = 200ms -> within radius, no click yet
    res2 = det.update((502, 501), t_ns=200_000_000)
    assert len(res2) == 0

    # Frame 3: stationary at t = 450ms (elapsed 450ms > 400ms) -> emits Click!
    res3 = det.update((503, 501), t_ns=450_000_000)
    assert len(res3) == 1
    assert isinstance(res3[0], Click)
    assert res3[0].button == Button.LEFT


def test_stability_mode_overrides() -> None:
    """Stability mode increases filter smoothing and widens pinch hysteresis."""
    cfg = AileronConfig()
    mgr = AccessibilityManager(cfg)
    mgr.apply_stability_mode_overrides()

    assert cfg.filters.cursor.min_cutoff == 0.6
    assert cfg.click.pinch_on == 0.28
    assert cfg.click.pinch_off == 0.40
    assert cfg.session.clutch_ms == 600


def test_hud_rendering_modes() -> None:
    """HudManager renders Compact and Full density modes without error."""
    hud = HudManager(mode=HudMode.COMPACT)
    canvas = np.zeros((480, 640, 3), dtype=np.uint8)

    out_compact = hud.render(canvas)
    assert out_compact.shape == (480, 640, 3)

    hud.mode = HudMode.FULL
    out_full = hud.render(canvas)
    assert out_full.shape == (480, 640, 3)
