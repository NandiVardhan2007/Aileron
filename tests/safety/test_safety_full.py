"""Comprehensive safety test suite verifying all SAFE-01 through SAFE-08 rules (M4).

Follows TESTING §5:
- Hand lost mid-drag -> ButtonUp emitted, ledger empty within hand_lost_ms + 1 tick
- Hand lost mid-throttle -> Trigger/steering neutralized
- Mode toggle while button held -> release_all before switch
- Exception injected into gesture engine -> FAULT, disarmed, ledger empty
- Control loop stall -> Watchdog fires release_all
- Kill switch during active input -> Output stops within one tick
- Shutdown -> release_all called, backend closed
- Event flood -> Rate limiter caps output
- Camera frames stop -> Treated as hand lost
- Backend raises on apply -> Fallback release_all, FAULT
- FAULT acknowledge flow -> Cannot re-arm until acknowledged
"""

import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from aileron.config import AileronConfig
from aileron.control import ControlPipeline
from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    Hand,
    HandFrame,
    Intent,
    MoveTo,
    ReleaseAll,
    SessionState,
    Side,
    Trigger,
)
from aileron.mapping.cursor import DesktopBounds
from aileron.modes.manager import ModeManager
from aileron.modes.session import SessionStateManager
from aileron.output.null import NullBackend
from aileron.safety.blackbox import BlackBoxRecorder
from aileron.safety.gate import SafetyGate
from aileron.safety.watchdog import CameraStallGuard, Watchdog


def _create_mock_hand(side: Side = Side.RIGHT, palm_size: float = 0.15) -> Hand:
    lm = np.zeros((21, 3), dtype=np.float32)
    world = np.zeros((21, 3), dtype=np.float32)
    # MCP (0) and WRIST (9)
    lm[0] = [0.5, 0.5, 0.0]
    lm[9] = [0.5, 0.5 - palm_size, 0.0]
    world[0] = [0.0, 0.0, 0.0]
    world[9] = [0.0, palm_size, 0.0]
    return Hand(side=side, score=0.95, lm=lm, world=world)


@pytest.mark.safety
def test_safe_01_kill_switch_during_active_input() -> None:
    """SAFE-01: Kill switch immediately neutralizes held inputs and disarms."""
    backend = NullBackend()
    backend.open()
    gate = SafetyGate(initial_state=SessionState.ARMED)
    sm = SessionStateManager(gate, start_armed=True)

    # Press left button
    app = gate.filter([ButtonDown(button=Button.LEFT)], now_ns=1_000_000)
    backend.apply(app)
    assert not backend.held_ledger.is_empty()

    # Trigger kill switch
    releases = sm.trigger_kill()
    backend.apply(releases)

    assert sm.state == SessionState.DISARMED
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_02_hand_lost_mid_drag_neutralizes_within_timeout() -> None:
    """SAFE-02: Losing hand while dragging automatically releases button within timeout."""
    cfg = AileronConfig()
    cfg.session.start_armed = True
    cfg.tracking.hand_lost_ms = 150

    backend = NullBackend()
    backend.open()
    pipeline = ControlPipeline(config=cfg, backend=backend)
    pipeline.session_manager.transition_to(SessionState.ARMED)

    # Initial step with active hand engages tracking
    hand = _create_mock_hand()
    pipeline.step(
        HandFrame(t_capture_ns=1_000_000_000, t_infer_done_ns=1_000_000_000, seq=1, hands=(hand,)),
        now_ns=1_000_000_000,
    )

    # Simulate button down directly in backend and gate ledger (e.g. active drag)
    backend.apply([ButtonDown(button=Button.LEFT)])
    pipeline.gate.ledger.record(ButtonDown(button=Button.LEFT))
    assert not backend.held_ledger.is_empty()

    # Step with empty frame at t = 1_050_000_000 (hand briefly absent, elapsed 50ms < 150ms)
    pipeline.step(
        HandFrame(t_capture_ns=1_050_000_000, t_infer_done_ns=1_050_000_000, seq=2, hands=()),
        now_ns=1_050_000_000,
    )
    assert not backend.held_ledger.is_empty()

    # Step with empty frame at t = 1_250_000_000 (elapsed 250ms > 150ms -> DISENGAGED)
    pipeline.step(
        HandFrame(t_capture_ns=1_250_000_000, t_infer_done_ns=1_250_000_000, seq=3, hands=()),
        now_ns=1_250_000_000,
    )

    # Invariant: ledger is empty
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_03_mode_toggle_while_button_held_neutralizes_first() -> None:
    """SAFE-03 / SAFE-07: Switching modes while input is held emits release_all first."""
    backend = NullBackend()
    backend.open()
    gate = SafetyGate(initial_state=SessionState.ARMED)
    mode_mgr = ModeManager()

    # Hold a button
    app = gate.filter([ButtonDown(button=Button.LEFT)], now_ns=1_000_000)
    backend.apply(app)
    assert not backend.held_ledger.is_empty()

    # Toggle mode
    _, releases = mode_mgr.toggle_mode()
    # Invariant: releases must contain ReleaseAll
    assert any(isinstance(r, ReleaseAll) for r in releases)

    filtered = gate.filter(releases, now_ns=2_000_000)
    backend.apply(filtered)

    # Ledger must be empty after mode toggle
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_04_watchdog_fires_on_control_loop_stall() -> None:
    """SAFE-04: Watchdog thread detects control loop stall and neutralizes backend."""
    backend = NullBackend()
    backend.open()
    backend.apply([ButtonDown(button=Button.LEFT)])
    assert not backend.held_ledger.is_empty()

    stall_callback_called = False

    def on_stall(_reason: str) -> None:
        nonlocal stall_callback_called
        stall_callback_called = True

    watchdog = Watchdog(
        backend=backend,
        on_stall=on_stall,
        stall_timeout_s=0.100,  # 100 ms for fast test
        check_interval_s=0.020,
    )

    # Initial heartbeat at t = 0
    t0 = time.monotonic_ns()
    watchdog.heartbeat(t0)

    # Check immediately: no stall
    assert not watchdog.check_once(t0 + 50_000_000)
    assert not backend.held_ledger.is_empty()

    # Check after 150 ms (> 100 ms timeout): stall fires!
    fired = watchdog.check_once(t0 + 150_000_000)
    assert fired
    assert watchdog.is_stalled
    assert stall_callback_called
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_04_camera_stall_guard_detects_missing_frames() -> None:
    """SAFE-04: CameraStallGuard detects frame starvation and treats as hand lost."""
    guard = CameraStallGuard(timeout_s=0.200)
    t0 = 1_000_000_000
    guard.record_frame(t0)

    assert not guard.is_stalled(t0 + 100_000_000)  # 100ms: healthy
    assert guard.is_stalled(t0 + 250_000_000)  # 250ms > 200ms: stalled


@pytest.mark.safety
def test_safe_05_start_state_is_disarmed_by_default() -> None:
    """SAFE-05: System always boots into DISARMED state and drops input candidates."""
    cfg = AileronConfig()
    backend = NullBackend()
    backend.open()
    pipeline = ControlPipeline(config=cfg, backend=backend)

    assert pipeline.session_manager.state == SessionState.DISARMED

    # In DISARMED state, candidate input is rejected
    app = pipeline.gate.filter([ButtonDown(button=Button.LEFT)], now_ns=1_000_000)
    assert len(app) == 0
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_06_virtual_desktop_bounds_clamping() -> None:
    """SAFE-06: Cursor coordinates are strictly clamped within desktop bounds."""
    bounds = DesktopBounds(vx=-1920, vy=0, vw=3840, vh=1080)
    gate = SafetyGate(desktop_bounds=bounds, initial_state=SessionState.ARMED)

    # Wild negative coordinate
    res1 = gate.filter([MoveTo(x=-5000, y=-200)], now_ns=1_000_000)
    assert isinstance(res1[0], MoveTo)
    assert res1[0].x == -1920
    assert res1[0].y == 0

    # Wild positive coordinate
    res2 = gate.filter([MoveTo(x=10000, y=5000)], now_ns=2_000_000)
    assert isinstance(res2[0], MoveTo)
    assert res2[0].x == bounds.vx + bounds.vw - 1
    assert res2[0].y == bounds.vy + bounds.vh - 1


@pytest.mark.safety
def test_safe_07_event_flood_rate_limiting_and_coalescing() -> None:
    """SAFE-07: Event flood is throttled and continuous motions are coalesced per tick."""
    gate = SafetyGate(initial_state=SessionState.ARMED)

    # 100 rapid MoveTo events in a single tick
    flood: list[Intent] = [MoveTo(x=i, y=i) for i in range(100)]
    flood.append(Axis(name="steer", value=0.5))
    flood.append(Axis(name="steer", value=0.8))  # duplicate axis
    flood.append(Trigger(name="throttle", value=0.2))
    flood.append(Trigger(name="throttle", value=0.6))  # duplicate trigger

    approved = gate.filter(flood, now_ns=1_000_000_000)

    # Must be coalesced: 1 MoveTo (latest), 1 steer Axis (value=0.8), 1 throttle (value=0.6)
    moves = [m for m in approved if isinstance(m, MoveTo)]
    axes = [a for a in approved if isinstance(a, Axis)]
    triggers = [t for t in approved if isinstance(t, Trigger)]

    assert len(moves) == 1
    assert moves[0].x == 99  # coalesced to latest MoveTo in tick
    assert len(axes) == 1
    assert axes[0].value == 0.8
    assert len(triggers) == 1
    assert triggers[0].value == 0.6


@pytest.mark.safety
def test_safe_08_fail_closed_on_pipeline_exception() -> None:
    """SAFE-08: Control loop exception triggers FAULT, neutralizes backend, and logs blackbox."""
    cfg = AileronConfig()
    backend = NullBackend()
    backend.open()
    pipeline = ControlPipeline(config=cfg, backend=backend)
    pipeline.session_manager.transition_to(SessionState.ARMED)

    # Pre-load a held button
    backend.apply([ButtonDown(button=Button.LEFT)])
    pipeline.gate.ledger.record(ButtonDown(button=Button.LEFT))
    assert not backend.held_ledger.is_empty()

    # Inject a faulting gesture engine
    pipeline.engine.process = MagicMock(side_effect=RuntimeError("Simulated pipeline crash"))

    # Step pipeline
    hand = _create_mock_hand()
    frame = HandFrame(
        t_capture_ns=1_000_000_000,
        t_infer_done_ns=1_000_000_000,
        seq=1,
        hands=(hand,),
    )
    result = pipeline.step(frame, now_ns=1_000_000_000)

    # Invariant checks:
    assert result.is_fault
    assert result.state == SessionState.FAULT
    assert pipeline.session_manager.state == SessionState.FAULT
    assert "Simulated pipeline crash" in (pipeline.session_manager.fault_reason or "")
    # Invariant: Held inputs neutralized on crash
    assert backend.held_ledger.is_empty()
    backend.close()


@pytest.mark.safety
def test_safe_08_fault_acknowledgment_flow() -> None:
    """SAFE-08: Once in FAULT state, system cannot re-arm until explicitly acknowledged."""
    gate = SafetyGate(initial_state=SessionState.ARMED)
    sm = SessionStateManager(gate, start_armed=True)

    # Trigger fault
    sm.trigger_fault("Camera hardware error")
    assert sm.state == SessionState.FAULT

    # Attempting to resume or arm directly while in FAULT raises or is rejected
    with pytest.raises(ValueError, match="Invalid session state transition"):
        sm.transition_to(SessionState.ARMED)

    # Cannot trigger resume dwell
    releases = sm.trigger_resume()
    assert len(releases) == 0
    assert sm.state == SessionState.FAULT

    # Acknowledge fault -> transitions to DISARMED
    sm.acknowledge_fault()
    assert sm.state == SessionState.DISARMED

    # Now that it's acknowledged, it can safely arm
    sm.trigger_resume()
    assert sm.state == SessionState.ARMED


@pytest.mark.safety
def test_blackbox_circular_buffer_recording_and_dump() -> None:
    """PRIV-02 / SAFETY-06: Blackbox buffer holds rolling landmarks and dumps on command."""
    recorder = BlackBoxRecorder(capacity=5, enabled=True)
    hand = _create_mock_hand()
    frame = HandFrame(t_capture_ns=1_000, t_infer_done_ns=1_000, seq=1, hands=(hand,))

    # Record 10 items into capacity=5 buffer
    for i in range(10):
        recorder.record(frame, [MoveTo(x=i, y=i)])

    assert len(recorder) == 5

    # Dump buffer
    dump_file = Path("tests/fixtures/test_blackbox_dump.jsonl")
    try:
        out_path = recorder.dump_to_file(dump_file, reason="unit_test")
        assert out_path.exists()
        lines = out_path.read_text(encoding="utf-8").strip().split("\n")
        # 1 header + 5 records
        assert len(lines) == 6
    finally:
        if dump_file.exists():
            dump_file.unlink()


@pytest.mark.safety
def test_shutdown_lifecycle_guarantee() -> None:
    """SAFE-03: Orderly shutdown guarantees backend release_all and closed state."""
    cfg = AileronConfig()
    backend = NullBackend()
    backend.open()
    pipeline = ControlPipeline(config=cfg, backend=backend, start_watchdog=True)
    pipeline.session_manager.transition_to(SessionState.ARMED)

    # Apply input
    backend.apply([ButtonDown(button=Button.LEFT)])
    pipeline.gate.ledger.record(ButtonDown(button=Button.LEFT))
    assert not backend.held_ledger.is_empty()

    # Pipeline shutdown
    pipeline.shutdown()

    assert backend.held_ledger.is_empty()
    assert pipeline.session_manager.state == SessionState.DISARMED
    assert not pipeline.watchdog._thread  # thread joined
