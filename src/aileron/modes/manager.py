"""Mode manager coordinating transitions between Pointer and Cockpit modes (M3).

Follows ARCHITECTURE §5.2:
- POINTER <-> COCKPIT mode toggle via Shaka dwell or hotkey
- Passes through neutral frame: release_all() -> switch -> HUD notification
- Safety: blocks mode toggle if Cockpit throttle > 0.3 to prevent runaway vehicle input
"""

from enum import Enum

from aileron.config import CockpitConfig
from aileron.interfaces import Intent, ReleaseAll


class ControlMode(Enum):
    """High-level operating mode."""

    POINTER = "pointer"
    COCKPIT = "cockpit"


class ModeManager:
    """Manages active interaction mode (POINTER vs COCKPIT) and profile switches."""

    def __init__(
        self,
        config: CockpitConfig | None = None,
        initial_mode: ControlMode = ControlMode.POINTER,
    ) -> None:
        self.config = config or CockpitConfig()
        self.mode: ControlMode = initial_mode
        self._last_mode_change_reason: str = "initial"

    @property
    def last_reason(self) -> str:
        """Reason description for the last mode change."""
        return self._last_mode_change_reason

    def toggle_mode(
        self, current_throttle: float = 0.0, reason: str = "Shaka dwell"
    ) -> tuple[ControlMode, list[Intent]]:
        """Toggle mode between POINTER and COCKPIT, enforcing safety throttle block."""
        if self.mode == ControlMode.POINTER:
            self.mode = ControlMode.COCKPIT
            self._last_mode_change_reason = reason
            # Neutral frame guarantee (ARCHITECTURE §5.2)
            return self.mode, [ReleaseAll()]

        # Cockpit -> Pointer: Check throttle block safety rule
        if current_throttle > self.config.mode_toggle_block_throttle:
            # Blocked: vehicle has active throttle!
            return self.mode, []

        self.mode = ControlMode.POINTER
        self._last_mode_change_reason = reason
        # Neutral frame guarantee
        return self.mode, [ReleaseAll()]

    def set_mode(
        self, target_mode: ControlMode, reason: str = "explicit"
    ) -> tuple[ControlMode, list[Intent]]:
        """Explicitly switch mode if permitted."""
        if target_mode == self.mode:
            return self.mode, []
        self.mode = target_mode
        self._last_mode_change_reason = reason
        return self.mode, [ReleaseAll()]
