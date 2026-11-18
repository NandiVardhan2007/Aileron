"""Safety-critical tests for M1 (SAFE-01..08), marked @pytest.mark.safety."""

from unittest.mock import MagicMock

import pytest

from aileron.config import ClickConfig
from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    Intent,
    Key,
    MoveBy,
    MoveTo,
    Pad,
    PadButton,
    ReleaseAll,
    Scroll,
    SessionState,
    Trigger,
    Zoom,
)
from aileron.mapping.cursor import DesktopBounds
from aileron.output.windows import WindowsMouseKeyboardBackend
from aileron.safety.gate import SafetyGate
from aileron.safety.kill_switch import (
    KillSwitchListener,
)
from aileron.safety.ledger import HeldInputLedger


@pytest.mark.safety
def test_disarmed_drops_all_intents() -> None:
    """SAFE-05: App starts DISARMED and emits no output until armed."""
    gate = SafetyGate(initial_state=SessionState.DISARMED)
    intents: list[Intent] = [MoveTo(x=500, y=500), ButtonDown(button=Button.LEFT)]

    approved = gate.filter(intents, now_ns=1000)
    assert len(approved) == 0
    assert gate.ledger.is_empty()

    # If ledger had held items while disarmed, filter must return draining releases
    gate.ledger.record(ButtonDown(button=Button.LEFT))
    drain = gate.filter([MoveTo(x=500, y=500)], now_ns=2000)
    assert any(isinstance(r, ButtonUp) for r in drain)
    assert gate.ledger.is_empty()


@pytest.mark.safety
def test_armed_allows_and_clamps() -> None:
    """SAFE-06: Coordinates are clamped to virtual desktop bounds."""
    bounds = DesktopBounds(vx=0, vy=0, vw=1920, vh=1080)
    gate = SafetyGate(desktop_bounds=bounds, initial_state=SessionState.ARMED)

    # Within bounds
    approved = gate.filter([MoveTo(x=100, y=100)], now_ns=1000)
    assert len(approved) == 1
    assert approved[0] == MoveTo(x=100, y=100)

    # Beyond desktop bounds -> clamped
    approved_clamp = gate.filter([MoveTo(x=2500, y=-50)], now_ns=2000)
    assert len(approved_clamp) == 1
    assert approved_clamp[0] == MoveTo(x=1919, y=0)


@pytest.mark.safety
def test_safety_gate_filtering_all_intent_types() -> None:
    """Verify rate-limiting and clamping for clicks, scrolls, zooms, axes, and triggers."""
    cfg = ClickConfig(max_clicks_per_s=2)
    gate = SafetyGate(click_cfg=cfg, initial_state=SessionState.ARMED)
    t0 = 1_000_000_000

    # 1. Clicks within rate limit
    c1 = gate.filter([Click(button=Button.LEFT, count=1)], now_ns=t0)
    assert len(c1) == 1
    c2 = gate.filter([Click(button=Button.LEFT, count=1)], now_ns=t0 + 100_000_000)
    assert len(c2) == 1

    # Exceeding rate limit -> dropped
    c3 = gate.filter([Click(button=Button.LEFT, count=1)], now_ns=t0 + 200_000_000)
    assert len(c3) == 0

    # Window expires after 1 second -> allowed again
    c4 = gate.filter([Click(button=Button.LEFT, count=1)], now_ns=t0 + 1_500_000_000)
    assert len(c4) == 1

    # 2. Scroll clamping
    sc = gate.filter([Scroll(dx=50.0, dy=-50.0)], now_ns=t0 + 1_600_000_000)
    assert len(sc) == 1
    assert isinstance(sc[0], Scroll)
    assert sc[0].dx <= 30.0
    assert sc[0].dy >= -30.0

    # 3. Zoom clamping
    zm = gate.filter([Zoom(steps=10)], now_ns=t0 + 1_700_000_000)
    assert len(zm) == 1
    assert isinstance(zm[0], Zoom)
    assert zm[0].steps == 3

    # 4. Axis clamping [-1.0 .. 1.0]
    ax = gate.filter([Axis(name="lx", value=2.5)], now_ns=t0 + 1_800_000_000)
    assert len(ax) == 1
    assert isinstance(ax[0], Axis)
    assert ax[0].value == 1.0

    # 5. Trigger clamping [0.0 .. 1.0]
    tr = gate.filter([Trigger(name="rt", value=-0.5)], now_ns=t0 + 1_900_000_000)
    assert len(tr) == 1
    assert isinstance(tr[0], Trigger)
    assert tr[0].value == 0.0

    # 6. ReleaseAll passed through gate
    rel = gate.filter([ReleaseAll()], now_ns=t0 + 2_000_000_000)
    assert any(isinstance(r, ReleaseAll) for r in rel)


@pytest.mark.safety
def test_safety_gate_state_transitions_and_heartbeat() -> None:
    """Verify state transitions and heartbeat watchdog detection."""
    gate = SafetyGate(initial_state=SessionState.ARMED)
    gate.ledger.record(ButtonDown(button=Button.LEFT))

    # Same state returns empty
    assert gate.set_state(SessionState.ARMED) == []

    # Changing state to STANDBY drains ledger
    releases = gate.set_state(SessionState.STANDBY)
    assert gate.state == SessionState.STANDBY
    assert any(isinstance(r, ButtonUp) for r in releases)
    assert gate.ledger.is_empty()

    # Heartbeat
    gate.heartbeat(1_000_000_000)
    assert not gate.is_heartbeat_stale(max_stale_ms=250, now_ns=1_100_000_000)
    assert gate.is_heartbeat_stale(max_stale_ms=250, now_ns=1_300_000_000)


@pytest.mark.safety
def test_held_ledger_comprehensive() -> None:
    """SAFE-03: Exercise all branch pathways in HeldInputLedger."""
    ledger = HeldInputLedger()
    ledger.record(ButtonDown(button=Button.LEFT))
    ledger.record(ButtonUp(button=Button.LEFT))
    assert ledger.is_empty()

    ledger.record(Key(chord="shift", down=True))
    ledger.record(Key(chord="shift", down=False))
    assert ledger.is_empty()

    ledger.record(Pad(button=PadButton.A, down=True))
    ledger.record(Pad(button=PadButton.A, down=False))
    assert ledger.is_empty()

    ledger.record(Axis(name="ly", value=0.5))
    assert "axis:ly" in ledger.held()
    ledger.record(Axis(name="ly", value=0.0))
    assert "axis:ly" not in ledger.held()

    ledger.record(Trigger(name="lt", value=0.7))
    assert "trigger:lt" in ledger.held()
    ledger.record(Trigger(name="lt", value=0.0))
    assert "trigger:lt" not in ledger.held()

    # ReleaseAll clears everything
    ledger.record(ButtonDown(button=Button.RIGHT))
    ledger.record(ReleaseAll())
    assert ledger.is_empty()


@pytest.mark.safety
def test_safety_gate_neutralize_fails_closed() -> None:
    """SAFE-08: Neutralize disarms, transitions to FAULT, and drains ledger."""
    gate = SafetyGate(initial_state=SessionState.ARMED)
    gate.filter([ButtonDown(button=Button.LEFT)], now_ns=1000)
    assert not gate.ledger.is_empty()

    releases = gate.neutralize()
    assert gate.state == SessionState.FAULT
    assert any(isinstance(r, ButtonUp) for r in releases)
    assert gate.ledger.is_empty()


@pytest.mark.safety
def test_windows_backend_mock_all_actions() -> None:
    """SAFE-03: Windows backend handles all intents and releases."""
    user32_mock = MagicMock()
    backend = WindowsMouseKeyboardBackend(user32_mock=user32_mock)
    backend.open()

    backend.apply(
        [
            MoveTo(x=100, y=200),
            MoveBy(dx=10, dy=-5),
            ButtonDown(button=Button.RIGHT),
            ButtonDown(button=Button.MIDDLE),
            ButtonUp(button=Button.RIGHT),
            ButtonUp(button=Button.MIDDLE),
            Click(button=Button.LEFT, count=1),
            Scroll(dx=2.0, dy=-3.0),
            Zoom(steps=2),
            Key(chord="ctrl", down=True),
            Key(chord="ctrl", down=False),
            ReleaseAll(),
        ]
    )

    assert len(backend.held()) == 0
    backend.close()


@pytest.mark.safety
def test_kill_switch_mock_lifecycle() -> None:
    """SAFE-01: Global kill switch start, stop, duplicate start, and manual trigger."""
    called = []

    def on_kill() -> None:
        called.append(True)

    user32_mock = MagicMock()
    user32_mock.GetMessageW.return_value = 0  # Loop exits immediately

    listener = KillSwitchListener(on_kill=on_kill, user32_mock=user32_mock)
    listener.start()
    # Duplicate start is a safe no-op
    listener.start()

    listener.trigger_manually()
    listener.stop()

    assert len(called) == 1
    assert user32_mock.RegisterHotKey.called
    assert user32_mock.UnregisterHotKey.called
