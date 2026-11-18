"""SafetyGate: Central enforcement of state gating, clamping, rate limits, and ledgers."""

import threading
import time
from collections import deque
from collections.abc import Sequence

from aileron.config import ClickConfig
from aileron.interfaces import (
    Axis,
    Click,
    Intent,
    MoveTo,
    ReleaseAll,
    Scroll,
    SessionState,
    Trigger,
    Zoom,
)
from aileron.mapping.cursor import DesktopBounds
from aileron.safety.ledger import HeldInputLedger

MAX_SCROLL_LINES_PER_TICK = 30.0
MAX_ZOOM_STEPS_PER_TICK = 3
ONE_SEC_NS = 1_000_000_000


class SafetyGate:
    """Enforces SAFE-01..10 invariants between mapping and actuation layers."""

    def __init__(
        self,
        click_cfg: ClickConfig | None = None,
        desktop_bounds: DesktopBounds | None = None,
        initial_state: SessionState = SessionState.DISARMED,
    ) -> None:
        self.click_cfg = click_cfg or ClickConfig()
        self.bounds = desktop_bounds or DesktopBounds.default()
        self._lock = threading.Lock()
        self._state: SessionState = initial_state
        self.ledger = HeldInputLedger()
        self._click_times_ns: deque[int] = deque()
        self._last_heartbeat_ns: int = time.monotonic_ns()

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    def set_state(self, new_state: SessionState) -> list[Intent]:
        """Transition session state and return any neutralizing releases."""
        with self._lock:
            if self._state == new_state:
                return []
            self._state = new_state
            return self.ledger.drain_and_create_releases()

    def heartbeat(self, now_ns: int) -> None:
        """Record heartbeat from control loop."""
        with self._lock:
            self._last_heartbeat_ns = now_ns

    def is_heartbeat_stale(self, max_stale_ms: int, now_ns: int) -> bool:
        """Check if control loop heartbeat is overdue."""
        with self._lock:
            elapsed_ms = (now_ns - self._last_heartbeat_ns) / 1_000_000.0
            return elapsed_ms > max_stale_ms

    def neutralize(self) -> list[Intent]:
        """Immediate failsafe neutralization."""
        with self._lock:
            self._state = SessionState.FAULT
            return self.ledger.drain_and_create_releases()

    def _filter_pointer_intent(self, intent: Intent, now_ns: int) -> Intent | None:
        match intent:
            case MoveTo(x=x, y=y):
                cx = max(self.bounds.vx, min(self.bounds.vx + self.bounds.vw - 1, x))
                cy = max(self.bounds.vy, min(self.bounds.vy + self.bounds.vh - 1, y))
                clamped = MoveTo(x=cx, y=cy)
                self.ledger.record(clamped)
                return clamped
            case Click(count=count):
                if len(self._click_times_ns) + count <= self.click_cfg.max_clicks_per_s:
                    for _ in range(count):
                        self._click_times_ns.append(now_ns)
                    self.ledger.record(intent)
                    return intent
                return None
            case Scroll(dx=dx, dy=dy):
                cdx = max(-MAX_SCROLL_LINES_PER_TICK, min(MAX_SCROLL_LINES_PER_TICK, dx))
                cdy = max(-MAX_SCROLL_LINES_PER_TICK, min(MAX_SCROLL_LINES_PER_TICK, dy))
                sc = Scroll(dx=cdx, dy=cdy)
                self.ledger.record(sc)
                return sc
            case Zoom(steps=steps):
                csteps = max(-MAX_ZOOM_STEPS_PER_TICK, min(MAX_ZOOM_STEPS_PER_TICK, steps))
                zm = Zoom(steps=csteps)
                self.ledger.record(zm)
                return zm
            case _:
                self.ledger.record(intent)
                return intent

    def _filter_gamepad_intent(self, intent: Intent) -> Intent:
        match intent:
            case Axis(name=name, value=val):
                cval = max(-1.0, min(1.0, val))
                ax = Axis(name=name, value=cval)
                self.ledger.record(ax)
                return ax
            case Trigger(name=name, value=val):
                cval = max(0.0, min(1.0, val))
                tr = Trigger(name=name, value=cval)
                self.ledger.record(tr)
                return tr
            case _:
                self.ledger.record(intent)
                return intent

    def filter(self, intents: Sequence[Intent], now_ns: int) -> list[Intent]:
        """Filter, clamp, rate-limit, and audit candidate intents."""
        with self._lock:
            if self._state != SessionState.ARMED:
                if not self.ledger.is_empty():
                    return self.ledger.drain_and_create_releases()
                return []

            approved: list[Intent] = []
            while self._click_times_ns and (now_ns - self._click_times_ns[0] > ONE_SEC_NS):
                self._click_times_ns.popleft()

            for intent in intents:
                if isinstance(intent, ReleaseAll):
                    approved.extend(self.ledger.drain_and_create_releases())
                elif isinstance(intent, MoveTo | Click | Scroll | Zoom):
                    res = self._filter_pointer_intent(intent, now_ns)
                    if res is not None:
                        approved.append(res)
                elif isinstance(intent, Axis | Trigger):
                    approved.append(self._filter_gamepad_intent(intent))
                else:
                    self.ledger.record(intent)
                    approved.append(intent)

            return approved
