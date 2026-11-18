"""Cockpit mode Yoke profile: Two-hand steering and trigger-finger pedals (M5).

Follows COCKPIT_MODE §2.1, §4, §5 and SIGNAL_PROCESSING §8, §10:
- Steering wheel angle from line L9 (Left) -> L9 (Right) in degrees.
- Deadzone (3°), expo response curve (0.35), lock-to-lock scaling (45°), One Euro filter.
- Pedals: Right index extension (throttle / RT), Left index extension (brake / LT).
- Neutral hold (1.0 s) before axes go live.
- Ramp-in (200 ms) when entering live state.
- Hand-loss neutralization (> 150 ms -> 0.0 or brake per on_loss config).
- Mode-toggle safety block when throttle > 0.3.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from aileron.config import CockpitConfig, CockpitYokeConfig, FiltersConfig
from aileron.filters.one_euro import OneEuroFilter1D
from aileron.interfaces import (
    Axis,
    Hand,
    HandFeatures,
    Intent,
    Pad,
    PadButton,
    Side,
    Trigger,
)
from aileron.landmarks import Lm

ASPECT_RATIO_DEFAULT = 16.0 / 9.0
ONE_SEC_MS = 1000.0
NEUTRAL_STEER_TOLERANCE_DEG = 5.0
NEUTRAL_PEDAL_TOLERANCE = 0.1
HAND_LOSS_STEER_HOLD_MS = 150.0


def shape_steering_axis(
    theta_deg: float,
    deadzone_deg: float,
    max_deg: float,
    expo: float,
) -> float:
    """Shape raw angle into normalized [-1.0, 1.0] axis with deadzone and expo curve."""
    abs_t = abs(theta_deg)
    if abs_t <= deadzone_deg:
        return 0.0

    # Range normalization beyond deadzone
    eff_range = max(max_deg - deadzone_deg, 1e-4)
    norm = min((abs_t - deadzone_deg) / eff_range, 1.0)

    # Expo curve: (1 - e) * x + e * x^3
    curved = (1.0 - expo) * norm + expo * (norm**3)
    return -curved if theta_deg < 0.0 else curved


def shape_trigger_axis(
    extension: float,
    ext_min: float,
    ext_max: float,
    deadzone: float,
    curve: float,
) -> float:
    """Shape finger extension into normalized [0.0, 1.0] trigger value."""
    rng = max(ext_max - ext_min, 1e-4)
    u = max(0.0, min(1.0, (extension - ext_min) / rng))
    if u <= deadzone:
        return 0.0

    eff_range = max(1.0 - deadzone, 1e-4)
    norm = (u - deadzone) / eff_range
    return float(norm**curve)


@dataclass(slots=True)
class YokeTelemetry:
    """Internal telemetry snapshot of Yoke profile."""

    steer_deg: float = 0.0
    steer_axis: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    is_live: bool = False
    neutral_hold_progress: float = 0.0


class YokeProfile:
    """Two-hand steering wheel and pedal controller for Cockpit mode."""

    def __init__(
        self,
        cockpit_cfg: CockpitConfig | None = None,
        yoke_cfg: CockpitYokeConfig | None = None,
        filters_cfg: FiltersConfig | None = None,
        neutral_deg: float = 0.0,
        aspect_ratio: float = ASPECT_RATIO_DEFAULT,
    ) -> None:
        self.cockpit_cfg = cockpit_cfg or CockpitConfig()
        self.yoke_cfg = yoke_cfg or CockpitYokeConfig()
        self.filters_cfg = filters_cfg or FiltersConfig()
        self.neutral_deg = neutral_deg
        self.aspect_ratio = aspect_ratio

        # Calibrated trigger ranges (curled, extended)
        self.right_ext_min = 0.30
        self.right_ext_max = 0.85
        self.left_ext_min = 0.30
        self.left_ext_max = 0.85

        # Filters
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
        self._last_two_hands_ns: int = 0
        self._last_steer_val: float = 0.0
        self.telemetry = YokeTelemetry()

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
        self._last_two_hands_ns = 0
        self._last_steer_val = 0.0
        self._steer_filter.reset()
        self._throttle_filter.reset()
        self._brake_filter.reset()
        self.telemetry = YokeTelemetry()

    def process(
        self,
        hands: Sequence[Hand],
        features: Sequence[HandFeatures],
        t_ns: int,
    ) -> list[Intent]:
        """Process hands and emit analog Axis, Trigger, and Pad intents."""
        left_h = next((h for h in hands if h.side == Side.LEFT), None)
        right_h = next((h for h in hands if h.side == Side.RIGHT), None)
        left_f = next((f for f in features if f.side == Side.LEFT), None)
        right_f = next((f for f in features if f.side == Side.RIGHT), None)

        # 1. Both hands tracked
        if left_h is not None and right_h is not None:
            self._last_two_hands_ns = t_ns
            return self._process_two_hands(left_h, right_h, left_f, right_f, t_ns)

        # 2. Hand loss or single hand fallback
        return self._process_hand_loss(t_ns)

    def _process_two_hands(
        self,
        left_h: Hand,
        right_h: Hand,
        left_f: HandFeatures | None,
        right_f: HandFeatures | None,
        t_ns: int,
    ) -> list[Intent]:
        """Compute steering wheel angle, throttle, and brake from both hands."""
        # Middle MCP (L9) coordinates
        p_l = left_h.lm[int(Lm.MIDDLE_FINGER_MCP)]
        p_r = right_h.lm[int(Lm.MIDDLE_FINGER_MCP)]

        # Steering angle in degrees (+ = clockwise wheel rotation)
        dx = float((p_r[0] - p_l[0]) * self.aspect_ratio)
        dy = float(p_r[1] - p_l[1])
        theta_raw = math.degrees(math.atan2(dy, dx))
        theta_adj = theta_raw - self.neutral_deg

        # Shaped steering in [-1.0, 1.0]
        raw_steer = shape_steering_axis(
            theta_adj,
            deadzone_deg=self.yoke_cfg.steer_deadzone_deg,
            max_deg=self.yoke_cfg.steer_max_deg,
            expo=self.yoke_cfg.steer_expo,
        )
        filtered_steer = self._steer_filter(raw_steer, t_ns)
        self._last_steer_val = filtered_steer

        # Throttle from right index extension
        r_ext = right_f.curl.get("index", 0.0) if right_f else 0.0
        raw_throttle = shape_trigger_axis(
            r_ext,
            self.right_ext_min,
            self.right_ext_max,
            self.yoke_cfg.trigger_deadzone,
            self.yoke_cfg.trigger_curve,
        )
        filtered_throttle = self._throttle_filter(raw_throttle, t_ns)

        # Brake from left index extension
        l_ext = left_f.curl.get("index", 0.0) if left_f else 0.0
        raw_brake = shape_trigger_axis(
            l_ext,
            self.left_ext_min,
            self.left_ext_max,
            self.yoke_cfg.trigger_deadzone,
            self.yoke_cfg.trigger_curve,
        )
        filtered_brake = self._brake_filter(raw_brake, t_ns)

        # Neutral hold evaluation
        if not self._axes_live:
            is_near_neutral = (
                abs(theta_adj) <= NEUTRAL_STEER_TOLERANCE_DEG
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

            # While not live, output stay neutral
            self.telemetry.is_live = False
            self.telemetry.steer_deg = theta_adj
            self.telemetry.steer_axis = 0.0
            self.telemetry.throttle = 0.0
            self.telemetry.brake = 0.0
            return [
                Axis(name="lx", value=0.0),
                Trigger(name="rt", value=0.0),
                Trigger(name="lt", value=0.0),
            ]

        # Live state: apply ramp-in
        scale = 1.0
        if self.cockpit_cfg.ramp_in_ms > 0:
            ramp_elapsed_ms = (t_ns - self._live_start_ns) / 1_000_000.0
            scale = min(ramp_elapsed_ms / self.cockpit_cfg.ramp_in_ms, 1.0)

        final_steer = max(-1.0, min(1.0, filtered_steer * scale))
        final_throttle = max(0.0, min(1.0, filtered_throttle * scale))
        final_brake = max(0.0, min(1.0, filtered_brake * scale))

        self.telemetry.is_live = True
        self.telemetry.steer_deg = theta_adj
        self.telemetry.steer_axis = final_steer
        self.telemetry.throttle = final_throttle
        self.telemetry.brake = final_brake

        intents: list[Intent] = [
            Axis(name="lx", value=final_steer),
            Trigger(name="rt", value=final_throttle),
            Trigger(name="lt", value=final_brake),
        ]

        # Button pinch combos (gear up / down, handbrake, horn)
        intents.extend(self._process_buttons(left_f, right_f))
        return intents

    def _process_buttons(
        self,
        left_f: HandFeatures | None,
        right_f: HandFeatures | None,
    ) -> list[Intent]:
        """Detect cockpit button pinch combos per COCKPIT_MODE §2.1."""
        btn_intents: list[Intent] = []
        pinch_thresh = 0.25

        if right_f is not None:
            # Gear up: right thumb + ring pinch -> RB
            if right_f.pinch.get("ring", 1.0) < pinch_thresh:
                btn_intents.append(Pad(button=PadButton.RB, down=True))
            # Handbrake: right thumb + pinky pinch -> X
            if right_f.pinch.get("pinky", 1.0) < pinch_thresh:
                btn_intents.append(Pad(button=PadButton.X, down=True))

        if left_f is not None:
            # Gear down: left thumb + ring pinch -> LB
            if left_f.pinch.get("ring", 1.0) < pinch_thresh:
                btn_intents.append(Pad(button=PadButton.LB, down=True))
            # Horn: left thumb + pinky pinch -> Y
            if left_f.pinch.get("pinky", 1.0) < pinch_thresh:
                btn_intents.append(Pad(button=PadButton.Y, down=True))

        return btn_intents

    def _process_hand_loss(self, t_ns: int) -> list[Intent]:
        """Handle single-hand or hand-lost conditions per COCKPIT_MODE §5."""
        elapsed_missing_ms = (t_ns - self._last_two_hands_ns) / 1_000_000.0

        if elapsed_missing_ms <= HAND_LOSS_STEER_HOLD_MS and self._axes_live:
            # Hold last steering for up to 150 ms (SIGNAL §8)
            return [
                Axis(name="lx", value=self._last_steer_val),
                Trigger(name="rt", value=0.0),
                Trigger(name="lt", value=0.0),
            ]

        # Missing > 150 ms: neutralize live state
        self._axes_live = False
        self._neutral_hold_start_ns = None
        self.telemetry.is_live = False
        self.telemetry.steer_axis = 0.0
        self.telemetry.throttle = 0.0

        if self.cockpit_cfg.on_loss == "brake":
            self.telemetry.brake = 1.0
            return [
                Axis(name="lx", value=0.0),
                Trigger(name="rt", value=0.0),
                Trigger(name="lt", value=1.0),
            ]

        self.telemetry.brake = 0.0
        return [
            Axis(name="lx", value=0.0),
            Trigger(name="rt", value=0.0),
            Trigger(name="lt", value=0.0),
        ]
