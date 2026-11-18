"""Unit tests for dwell gestures, SessionStateManager, and ModeManager (M3)."""

import numpy as np
import pytest

from aileron.config import CockpitConfig, FingersConfig, SessionConfig, TrackingConfig
from aileron.gestures.dwell import DwellGestureDetector
from aileron.interfaces import GestureKind, HandFeatures, ReleaseAll, SessionState, Side
from aileron.modes.manager import ControlMode, ModeManager
from aileron.modes.session import SessionStateManager
from aileron.safety.gate import SafetyGate


def _make_feat_with_curls(
    curls: dict[str, float],
    pinch: dict[str, float] | None = None,
    palm_z: float = 0.9,
) -> tuple[HandFeatures]:
    p = pinch or {"index": 0.6, "middle": 0.6, "ring": 0.6, "pinky": 0.6}
    hf = HandFeatures(
        side=Side.RIGHT,
        valid=True,
        palm_size=0.15,
        anchor=(0.5, 0.5),
        curl=curls,
        pinch=p,
        roll_deg=0.0,
        palm_normal=np.array([0.0, 0.0, palm_z], dtype=np.float32),
        palm_center=(0.5, 0.5),
    )
    return (hf,)


def test_clutch_fist_dwell_triggers_standby() -> None:
    """Holding fist for 400ms in ARMED emits CLUTCH and transitions session to STANDBY."""
    s_cfg = SessionConfig(clutch_ms=400, resume_ms=400, arm_ms=800, mode_ms=800)
    f_cfg = FingersConfig(ext_on=0.75, ext_off=0.35)
    t_cfg = TrackingConfig(dwell_grace_ms=100)
    det = DwellGestureDetector(s_cfg, f_cfg, t_cfg)

    # Fist features: all fingers curled < 0.35, pinch > 0.4
    fist = _make_feat_with_curls(
        {"thumb": 0.1, "index": 0.1, "middle": 0.1, "ring": 0.1, "pinky": 0.1},
        pinch={"index": 0.6, "middle": 0.6, "ring": 0.6, "pinky": 0.6},
    )

    # Start fist at t = 0
    det.update_with_state(fist, t_ns=0, session_state=SessionState.ARMED)
    assert det.clutch_timer.progress == 0.0

    # At t = 200ms: progress is ~0.5
    det.update_with_state(fist, t_ns=200_000_000, session_state=SessionState.ARMED)
    assert 0.45 <= det.clutch_timer.progress <= 0.55
    assert "clutch" in det.progress_dict

    # At t = 400ms: reaches 400ms -> emits CLUTCH
    evs = det.update_with_state(fist, t_ns=400_000_000, session_state=SessionState.ARMED)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.CLUTCH


def test_resume_open_palm_dwell() -> None:
    """Holding open palm for 400ms in STANDBY emits RESUME."""
    s_cfg = SessionConfig(clutch_ms=400, resume_ms=400, arm_ms=800, mode_ms=800)
    f_cfg = FingersConfig()
    t_cfg = TrackingConfig()
    det = DwellGestureDetector(s_cfg, f_cfg, t_cfg)

    palm = _make_feat_with_curls(
        {"thumb": 0.9, "index": 0.9, "middle": 0.9, "ring": 0.9, "pinky": 0.9},
        palm_z=0.8,
    )

    det.update_with_state(palm, t_ns=0, session_state=SessionState.STANDBY)
    evs = det.update_with_state(palm, t_ns=400_000_000, session_state=SessionState.STANDBY)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.RESUME


def test_mode_toggle_shaka_dwell() -> None:
    """Holding shaka for 800ms in ARMED emits MODE_TOGGLE."""
    s_cfg = SessionConfig(mode_ms=800)
    f_cfg = FingersConfig()
    t_cfg = TrackingConfig()
    det = DwellGestureDetector(s_cfg, f_cfg, t_cfg)

    # Shaka: thumb and pinky extended, index, middle, ring curled
    shaka = _make_feat_with_curls(
        {"thumb": 0.85, "index": 0.1, "middle": 0.1, "ring": 0.1, "pinky": 0.85}
    )

    det.update_with_state(shaka, t_ns=0, session_state=SessionState.ARMED)
    det.update_with_state(shaka, t_ns=400_000_000, session_state=SessionState.ARMED)
    assert "mode_toggle" in det.progress_dict
    assert 0.45 <= det.mode_timer.progress <= 0.55

    evs = det.update_with_state(shaka, t_ns=800_000_000, session_state=SessionState.ARMED)
    assert len(evs) == 1
    assert evs[0].kind == GestureKind.MODE_TOGGLE


def test_dwell_grace_period_tolerance() -> None:
    """SIG-12: A brief pose interruption (< dwell_grace_ms=100ms) pauses progress.

    Progress pauses rather than resetting immediately.
    """
    s_cfg = SessionConfig(clutch_ms=400)
    f_cfg = FingersConfig()
    t_cfg = TrackingConfig(dwell_grace_ms=100)
    det = DwellGestureDetector(s_cfg, f_cfg, t_cfg)

    fist = _make_feat_with_curls(
        {"thumb": 0.1, "index": 0.1, "middle": 0.1, "ring": 0.1, "pinky": 0.1}
    )

    # 1. Start dwell: t = 0 -> 200ms
    det.update_with_state(fist, t_ns=0, session_state=SessionState.ARMED)
    det.update_with_state(fist, t_ns=200_000_000, session_state=SessionState.ARMED)
    prog_before = det.clutch_timer.progress
    assert prog_before > 0.4

    # 2. Glitch for 50ms (< 100ms grace) at t = 250ms
    det.update_with_state((), t_ns=250_000_000, session_state=SessionState.ARMED)
    # Timer did not reset to 0!
    assert det.clutch_timer.progress == prog_before

    # 3. Fist reappears at t = 270ms: resumes accumulating
    det.update_with_state(fist, t_ns=270_000_000, session_state=SessionState.ARMED)
    assert det.clutch_timer.progress > prog_before

    # 4. Long glitch for 150ms (> 100ms grace) -> resets
    det.update_with_state((), t_ns=450_000_000, session_state=SessionState.ARMED)
    assert det.clutch_timer.progress == 0.0


def test_session_state_manager_transitions() -> None:
    """Verify SessionStateManager transitions and invariant ReleaseAll emission."""
    gate = SafetyGate(initial_state=SessionState.DISARMED)
    sm = SessionStateManager(gate, start_armed=False)
    assert sm.state == SessionState.DISARMED

    # Arm
    sm.trigger_resume()
    assert sm.state == SessionState.ARMED

    # Clutch -> Standby
    rel_clutch = sm.trigger_clutch()
    assert sm.state == SessionState.STANDBY
    assert any(isinstance(r, ReleaseAll) for r in rel_clutch)

    # Resume -> Armed
    sm.trigger_resume()
    assert sm.state == SessionState.ARMED

    # Kill -> Disarmed
    rel_kill = sm.trigger_kill()
    assert sm.state == SessionState.DISARMED
    assert any(isinstance(r, ReleaseAll) for r in rel_kill)

    # Fault and acknowledge
    sm.trigger_fault("Camera stall")
    assert sm.state == SessionState.FAULT
    assert sm.fault_reason == "Camera stall"
    sm.acknowledge_fault()
    assert sm.state == SessionState.DISARMED
    assert sm.fault_reason is None

    # Invalid transition raises ValueError
    with pytest.raises(ValueError):
        sm.transition_to(SessionState.STANDBY)  # DISARMED -> STANDBY is invalid


def test_mode_manager_toggle_and_safety_throttle_block() -> None:
    """Verify ModeManager POINTER <-> COCKPIT toggle with neutral frame and throttle block."""
    cfg = CockpitConfig(mode_toggle_block_throttle=0.3)
    mm = ModeManager(cfg, initial_mode=ControlMode.POINTER)

    # Pointer -> Cockpit emits ReleaseAll
    m1, rel1 = mm.toggle_mode()
    assert m1 == ControlMode.COCKPIT
    assert any(isinstance(r, ReleaseAll) for r in rel1)

    # Cockpit -> Pointer blocked if throttle > 0.3!
    m_blocked, rel_blocked = mm.toggle_mode(current_throttle=0.45)
    assert m_blocked == ControlMode.COCKPIT
    assert len(rel_blocked) == 0  # Blocked!

    # Cockpit -> Pointer allowed when throttle <= 0.3
    m_ok, rel_ok = mm.toggle_mode(current_throttle=0.10)
    assert m_ok == ControlMode.POINTER
    assert any(isinstance(r, ReleaseAll) for r in rel_ok)
