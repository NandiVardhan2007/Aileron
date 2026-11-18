"""Pre-flight calibration wizard for Cockpit and Pointer profiles (M5).

Follows CALIBRATION_UX §1-4:
- Neutral angle calibration (hands held level on wheel).
- Lock-to-lock comfortable range calibration (comfortable maximum steering angle).
- Trigger finger calibration (curled vs extended range per hand).
- Persists calibrated values into user profile TOML files.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from aileron.interfaces import Hand, HandFeatures, Side
from aileron.landmarks import Lm

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(slots=True)
class CalibrationData:
    """Calibrated biometric and posture parameters."""

    neutral_angle_deg: float = 0.0
    steer_max_deg: float = 45.0
    right_trigger_min: float = 0.30
    right_trigger_max: float = 0.85
    left_trigger_min: float = 0.30
    left_trigger_max: float = 0.85


class CalibrationWizard:
    """Interactive and programmatic calibration engine."""

    def __init__(self, aspect_ratio: float = 16.0 / 9.0) -> None:
        self.aspect_ratio = aspect_ratio
        self.data = CalibrationData()

    def compute_steering_angle(self, left_hand: Hand, right_hand: Hand) -> float:
        """Compute instantaneous wheel angle between L9 of left and right hands."""
        p_l = left_hand.lm[int(Lm.MIDDLE_FINGER_MCP)]
        p_r = right_hand.lm[int(Lm.MIDDLE_FINGER_MCP)]

        dx = float((p_r[0] - p_l[0]) * self.aspect_ratio)
        dy = float(p_r[1] - p_l[1])
        return math.degrees(math.atan2(dy, dx))

    def calibrate_neutral(self, samples: Sequence[tuple[Hand, Hand]]) -> float:
        """Calculate mean neutral wheel angle from stationary level samples."""
        if not samples:
            return 0.0

        angles = [self.compute_steering_angle(lh, rh) for lh, rh in samples]
        self.data.neutral_angle_deg = float(np.median(angles))
        return self.data.neutral_angle_deg

    def calibrate_lock(
        self,
        samples_left: Sequence[tuple[Hand, Hand]],
        samples_right: Sequence[tuple[Hand, Hand]],
    ) -> float:
        """Calculate comfortable lock-to-lock angle from maximum turn samples."""
        angles_left = [
            abs(self.compute_steering_angle(lh, rh) - self.data.neutral_angle_deg)
            for lh, rh in samples_left
        ]
        angles_right = [
            abs(self.compute_steering_angle(lh, rh) - self.data.neutral_angle_deg)
            for lh, rh in samples_right
        ]

        max_l = float(np.percentile(angles_left, 90)) if angles_left else 45.0
        max_r = float(np.percentile(angles_right, 90)) if angles_right else 45.0
        lock_deg = float(np.clip((max_l + max_r) / 2.0, 20.0, 75.0))
        self.data.steer_max_deg = lock_deg
        return lock_deg

    def calibrate_triggers(
        self,
        rest_features: Sequence[HandFeatures],
        extended_features: Sequence[HandFeatures],
        side: Side,
    ) -> tuple[float, float]:
        """Calculate trigger min and max extension for specified hand."""
        rest_exts = [
            f.curl.get("index", 0.3) for f in rest_features if f.side == side and "index" in f.curl
        ]
        ext_exts = [
            f.curl.get("index", 0.8)
            for f in extended_features
            if f.side == side and "index" in f.curl
        ]

        min_val = float(np.median(rest_exts)) if rest_exts else 0.30
        max_val = float(np.median(ext_exts)) if ext_exts else 0.85

        if side == Side.RIGHT:
            self.data.right_trigger_min = min_val
            self.data.right_trigger_max = max(max_val, min_val + 0.20)
            return (self.data.right_trigger_min, self.data.right_trigger_max)

        self.data.left_trigger_min = min_val
        self.data.left_trigger_max = max(max_val, min_val + 0.20)
        return (self.data.left_trigger_min, self.data.left_trigger_max)

    def save_profile_toml(self, path: str | Path) -> Path:
        """Export calibrated profile parameters to TOML."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        content = (
            "# Aileron Calibrated Profile\n"
            'profile = "yoke"\n\n'
            "[cockpit.yoke]\n"
            f"neutral_deg = {self.data.neutral_angle_deg:.2f}\n"
            f"steer_max_deg = {self.data.steer_max_deg:.2f}\n"
            f"right_trigger_min = {self.data.right_trigger_min:.3f}\n"
            f"right_trigger_max = {self.data.right_trigger_max:.3f}\n"
            f"left_trigger_min = {self.data.left_trigger_min:.3f}\n"
            f"left_trigger_max = {self.data.left_trigger_max:.3f}\n"
        )
        target.write_text(content, encoding="utf-8")
        return target
