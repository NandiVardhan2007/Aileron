"""Session state manager enforcing valid transitions and safety releases (M3).

Follows ARCHITECTURE §5.1:
  BOOT -> DISARMED
  DISARMED -> ARMED (arm dwell / hotkey)
  ARMED -> STANDBY (clutch dwell)
  STANDBY -> ARMED (resume dwell)
  ARMED/STANDBY -> DISARMED (kill switch)
  ARMED/STANDBY -> FAULT (exception / watchdog)
  FAULT -> DISARMED (user acknowledge)
"""

from aileron.interfaces import Intent, ReleaseAll, SessionState
from aileron.safety.gate import SafetyGate


class SessionStateManager:
    """Manages active session lifecycle state and synchronizes with SafetyGate."""

    def __init__(
        self,
        safety_gate: SafetyGate,
        start_armed: bool = False,
    ) -> None:
        self.gate = safety_gate
        self.state: SessionState = SessionState.BOOT
        self._fault_reason: str | None = None

        # Transition to initial operating state
        initial = SessionState.ARMED if start_armed else SessionState.DISARMED
        self.transition_to(initial)

    @property
    def fault_reason(self) -> str | None:
        """Reason description if currently in FAULT state."""
        return self._fault_reason

    def transition_to(self, new_state: SessionState, reason: str | None = None) -> list[Intent]:
        """Transition to a new SessionState, updating SafetyGate and draining releases."""
        if new_state == self.state:
            return []

        # Validate transition matrix
        if not self._can_transition(self.state, new_state):
            raise ValueError(
                f"Invalid session state transition from {self.state.value} to {new_state.value}"
            )

        self.state = new_state
        if new_state == SessionState.FAULT:
            self._fault_reason = reason or "Unspecified safety fault"
        elif new_state == SessionState.DISARMED and self._fault_reason is not None:
            self._fault_reason = None

        # Synchronize with SafetyGate
        releases = self.gate.set_state(new_state)

        # Invariant: Entering any state other than ARMED ensures all inputs are released
        if new_state != SessionState.ARMED and not any(isinstance(r, ReleaseAll) for r in releases):
            releases.append(ReleaseAll())

        return releases

    def trigger_clutch(self) -> list[Intent]:
        """Handle clutch dwell trigger (ARMED -> STANDBY)."""
        if self.state == SessionState.ARMED:
            return self.transition_to(SessionState.STANDBY, reason="Clutch dwell gesture")
        return []

    def trigger_resume(self) -> list[Intent]:
        """Handle resume dwell trigger (STANDBY -> ARMED or DISARMED -> ARMED)."""
        if self.state in (SessionState.STANDBY, SessionState.DISARMED):
            return self.transition_to(SessionState.ARMED, reason="Resume / arm dwell gesture")
        return []

    def trigger_kill(self) -> list[Intent]:
        """Handle global kill switch or panic (-> DISARMED)."""
        return self.transition_to(SessionState.DISARMED, reason="Kill switch triggered")

    def trigger_fault(self, reason: str) -> list[Intent]:
        """Handle unrecoverable loop exception or watchdog stall (-> FAULT)."""
        return self.transition_to(SessionState.FAULT, reason=reason)

    def acknowledge_fault(self) -> list[Intent]:
        """Handle user acknowledgment to recover from FAULT state (FAULT -> DISARMED)."""
        if self.state == SessionState.FAULT:
            return self.transition_to(SessionState.DISARMED, reason="Fault acknowledged by user")
        return []

    @staticmethod
    def _can_transition(curr: SessionState, target: SessionState) -> bool:
        """Validate state transition rules per ARCHITECTURE §5.1."""
        valid_transitions: dict[SessionState, set[SessionState]] = {
            SessionState.BOOT: {SessionState.DISARMED, SessionState.ARMED, SessionState.FAULT},
            SessionState.DISARMED: {SessionState.ARMED, SessionState.FAULT},
            SessionState.ARMED: {SessionState.STANDBY, SessionState.DISARMED, SessionState.FAULT},
            SessionState.STANDBY: {SessionState.ARMED, SessionState.DISARMED, SessionState.FAULT},
            SessionState.FAULT: {SessionState.DISARMED},
        }
        return target in valid_transitions.get(curr, set())
