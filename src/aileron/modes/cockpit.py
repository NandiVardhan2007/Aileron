"""Cockpit mode engine coordinator (M5).

Follows ARCHITECTURE §5.2 and COCKPIT_MODE §1-5:
- Coordinates active cockpit profile (Yoke default, Handlebar M6).
- Forwards analog Axis and Trigger intents to control loop.
- Monitors current throttle to block mode toggle when throttle > 0.3.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from aileron.config import CockpitConfig, FiltersConfig
from aileron.interfaces import Hand, HandFeatures, Intent
from aileron.modes.yoke import YokeProfile, YokeTelemetry

if TYPE_CHECKING:
    from aileron.modes.manager import ModeManager


class CockpitEngine:
    """Dispatches simulator profiles and telemetry in Cockpit mode."""

    def __init__(
        self,
        config: CockpitConfig | None = None,
        filters_cfg: FiltersConfig | None = None,
        mode_manager: ModeManager | None = None,
    ) -> None:
        self.config = config or CockpitConfig()
        self.filters_cfg = filters_cfg or FiltersConfig()
        self.mode_manager = mode_manager

        # Initialize profiles
        self.yoke = YokeProfile(
            cockpit_cfg=self.config,
            filters_cfg=self.filters_cfg,
        )

    @property
    def current_throttle(self) -> float:
        """Current throttle output from the active profile."""
        return self.yoke.current_throttle

    @property
    def telemetry(self) -> YokeTelemetry:
        """Active profile telemetry for HUD and diagnostic viewers."""
        return self.yoke.telemetry

    def reset(self) -> None:
        """Reset state across all simulator profiles."""
        self.yoke.reset()

    def process(
        self,
        hands: Sequence[Hand],
        features: Sequence[HandFeatures],
        t_ns: int,
    ) -> list[Intent]:
        """Process tracking inputs through the active cockpit profile."""
        intents = self.yoke.process(hands, features, t_ns)

        # Notify ModeManager of current throttle to enforce safety toggle block
        if self.mode_manager is not None:
            self.mode_manager.current_throttle = self.current_throttle

        return intents
