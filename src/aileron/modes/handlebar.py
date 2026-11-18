"""Cockpit mode Handlebar profile: Single-hand roll steering and throttle (M6).

Follows COCKPIT_MODE §2.2 and SIGNAL_PROCESSING §9:
- Hand roll (wrist L0 -> middle MCP L9) maps to steering / bike lean (±35°).
- Deadzone (3°), expo curve (0.35), One Euro steering filter.
- Configurable throttle source: "thumb_curl" (default), "wrist_twist", or "index".
- Brake from off-hand index extension if available.
- Neutral hold (1.0 s) and ramp-in (200 ms).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from aileron.config import CockpitConfig, CockpitHandlebarConfig, FiltersConfig
from aileron.filters.one_euro import OneEuroFilter1D
from aileron.interfaces import (
    Axis,
    Hand,
    HandFeatures,
    Intent,
    Side,
    Trigger,
)
from aileron.landmarks import Lm
from aileron.modes.yoke import (
    shape_steering_axis,
    shape_trigger_axis,
)

HAND_LOSS_STEER_HOLD_MS = 150.0
NEUTRAL_ROLL_TOLERANCE_DEG = 5.0
NEUTRAL_PEDAL_TOLERANCE = 0.1


@dataclass(slots=True)
class HandlebarTelemetry:
    """Internal telemetry snapshot of Handlebar profile."""

    roll_deg: float = 0.0
    steer_axis: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    is_live: bool = False
    neutral_hold_progress: float = 0.0


class HandlebarProfile:
    """Motorcycle / bike handlebar controller using single-hand lean and throttle."""

    def __init__(
        self,
        cockpit_cfg: CockpitConfig | None = None,
        handlebar_cfg: CockpitHandlebarConfig | None = None,
        filters_cfg: FiltersConfig | None = None,
        neutral_roll_deg: float = 0.0,
    ) -> None:
        self.cockpit_cfg = cockpit_cfg or CockpitConfig()
        self.handlebar_cfg = handlebar_cfg or CockpitHandlebarConfig()
        self.filters_cfg = filters_cfg or FiltersConfig()
        self.neutral_roll_deg = neutral_roll_deg

        # Filter instances
        self._steer_filter = OneEuroFilter1D(
            min_cutoff=self.filters_cfg.steering.min_cutoff,
            beta=self.filters_cfg.steering.beta,
            d_cutoff=self.filters_cfg.steering.d_cutoff,
        )
        self._throttle_filter = OneEuroFilter1D(
            min_cutoff=self.filters_cfg.trigger.min_cutoff,
            beta=self.filters_cfg.trigger.beta,
            d_cutoff=self.filters_cfg.trigger.d_cutoff,
        )
        self._brake_filter = OneEuroFilter1D(
            min_cutoff=self.filters_cfg.trigger.min_cutoff,
            beta=self.filters_cfg.trigger.beta,
            d_cutoff=self.filters_cfg.trigger.d_cutoff,
        )

        # State tracking
        self._axes_live = False
        self._neutral_hold_start_ns: int | None = None
        self._live_start_ns: int = 0
        self._last_seen_ns: int = 0
        self._last_steer_val: float = 0.0
        self.telemetry = HandlebarTelemetry()

    @property
    def is_axes_live(self) -> bool:
        """Whether controller axes have passed neutral hold and are live."""
        return self._axes_live

    @property
    def current_throttle(self) -> float:
        """Current throttle output in [0.0, 1.0]."""
        return self.telemetry.throttle

    def reset(self) -> None:
        """Reset state, filters, and neutral hold timer."""
        self._axes_live = False
        self._neutral_hold_start_ns = None
        self._live_start_ns = 0
        self._last_seen_ns = 0
        self._last_steer_val = 0.0
        self._steer_filter.reset()
        self._throttle_filter.reset()
        self._brake_filter.reset()
        self.telemetry = HandlebarTelemetry()

    def process(
        self,
        hands: Sequence[Hand],
        features: Sequence[HandFeatures],
        t_ns: int,
    ) -> list[Intent]:
        """Compute steering from hand roll and throttle/brake from hand features."""
        if not hands:
            return self._process_hand_loss(t_ns)

        # Primary steering hand (prefer right hand, fallback to any visible hand)
        steer_h = next((h for h in hands if h.side == Side.RIGHT), hands[0])
        steer_f = next((f for f in features if f.side == steer_h.side), None)
        off_f = next((f for f in features if f.side != steer_h.side), None)

        self._last_seen_ns = t_ns

        # 1. Hand roll angle: vector from wrist (L0) to middle MCP (L9) in 3D world space
        v = steer_h.world[int(Lm.MIDDLE_FINGER_MCP)] - steer_h.world[int(Lm.WRIST)]
        # Roll: 0 = vertical, + = tilted right (clockwise)
        roll_deg = math.degrees(math.atan2(float(v[0]), -float(v[1])))
        roll_adj = roll_deg - self.neutral_roll_deg

        # Shape steering axis
        raw_steer = shape_steering_axis(
            roll_adj,
            deadzone_deg=self.handlebar_cfg.steer_deadzone_deg,
            max_deg=self.handlebar_cfg.steer_max_deg,
            expo=self.handlebar_cfg.steer_expo,
        )
        filtered_steer = self._steer_filter(raw_steer, t_ns)
        self._last_steer_val = filtered_steer

        # 2. Throttle computation
        raw_throttle = self._compute_throttle(steer_f)
        filtered_throttle = self._throttle_filter(raw_throttle, t_ns)

        # 3. Brake computation (from off-hand index extension if available)
        raw_brake = 0.0
        if off_f is not None and "index" in off_f.curl:
            raw_brake = shape_trigger_axis(
                off_f.curl["index"],
                ext_min=0.30,
                ext_max=0.85,
                deadzone=0.05,
                curve=1.0,
            )
        filtered_brake = self._brake_filter(raw_brake, t_ns)

        # 4. Neutral hold check
        if not self._axes_live:
            is_near_neutral = (
                abs(roll_adj) <= NEUTRAL_ROLL_TOLERANCE_DEG
                and raw_throttle <= NEUTRAL_PEDAL_TOLERANCE
                and raw_brake <= NEUTRAL_PEDAL_TOLERANCE
            )
            if is_near_neutral:
                if self._neutral_hold_start_ns is None:
                    self._neutral_hold_start_ns = t_ns
                elapsed_ms = (t_ns - self._neutral_hold_start_ns) / 1_000_000.0
                prog = min(elapsed_ms / max(self.cockpit_cfg.neutral_hold_ms, 1), 1.0)
                self.telemetry.neutral_hold_progress = prog
                if elapsed_ms >= self.cockpit_cfg.neutral_hold_ms:
                    self._axes_live = True
                    self._live_start_ns = t_ns
            else:
                self._neutral_hold_start_ns = None
                self.telemetry.neutral_hold_progress = 0.0

            self.telemetry.is_live = False
            self.telemetry.roll_deg = roll_adj
            self.telemetry.steer_axis = 0.0
            self.telemetry.throttle = 0.0
            self.telemetry.brake = 0.0
            return [
                Axis(name="lx", value=0.0),
                Trigger(name="rt", value=0.0),
                Trigger(name="lt", value=0.0),
            ]

        # 5. Live ramp-in
        scale = 1.0
        if self.cockpit_cfg.ramp_in_ms > 0:
            ramp_elapsed_ms = (t_ns - self._live_start_ns) / 1_000_000.0
            scale = min(ramp_elapsed_ms / self.cockpit_cfg.ramp_in_ms, 1.0)

        final_steer = max(-1.0, min(1.0, filtered_steer * scale))
        final_throttle = max(0.0, min(1.0, filtered_throttle * scale))
        final_brake = max(0.0, min(1.0, filtered_brake * scale))

        self.telemetry.is_live = True
        self.telemetry.roll_deg = roll_adj
        self.telemetry.steer_axis = final_steer
        self.telemetry.throttle = final_throttle
        self.telemetry.brake = final_brake

        return [
            Axis(name="lx", value=final_steer),
            Trigger(name="rt", value=final_throttle),
            Trigger(name="lt", value=final_brake),
        ]

    def _compute_throttle(self, features: HandFeatures | None) -> float:
        """Compute throttle value according to configured throttle_source."""
        if features is None:
            return 0.0

        source = self.handlebar_cfg.throttle_source
        if source == "thumb_curl":
            # Thumb curled toward palm: smaller pinch distance -> higher throttle
            pinch_dist = features.pinch.get("index", 1.0)
            u = max(0.0, min(1.0, (0.50 - pinch_dist) / 0.35))
            return shape_trigger_axis(u, ext_min=0.0, ext_max=1.0, deadzone=0.05, curve=1.0)

        if source == "index":
            ext = features.curl.get("index", 0.0)
            return shape_trigger_axis(ext, ext_min=0.30, ext_max=0.85, deadzone=0.05, curve=1.0)

        if source == "wrist_twist":
            # Normal vector rotation
            normal_y = float(features.palm_normal[1])
            u = max(0.0, min(1.0, (normal_y + 0.5) / 1.0))
            return shape_trigger_axis(u, ext_min=0.0, ext_max=1.0, deadzone=0.05, curve=1.0)

        return 0.0

    def _process_hand_loss(self, t_ns: int) -> list[Intent]:
        """Neutralize outputs when steering hand is lost."""
        elapsed_ms = (t_ns - self._last_seen_ns) / 1_000_000.0

        if elapsed_ms <= HAND_LOSS_STEER_HOLD_MS and self._axes_live:
            return [
                Axis(name="lx", value=self._last_steer_val),
                Trigger(name="rt", value=0.0),
                Trigger(name="lt", value=0.0),
            ]

        self._axes_live = False
        self._neutral_hold_start_ns = None
        self.telemetry.is_live = False
        self.telemetry.steer_axis = 0.0
        self.telemetry.throttle = 0.0
        self.telemetry.brake = 0.0

        return [
            Axis(name="lx", value=0.0),
            Trigger(name="rt", value=0.0),
            Trigger(name="lt", value=0.0),
        ]
