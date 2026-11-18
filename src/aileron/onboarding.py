"""Interactive and programmatic user onboarding flow (M6).

Follows CALIBRATION_UX §2:
- Step 1: Privacy statement ("video never leaves this computer").
- Step 2: Camera check: live preview, lighting check, framing guide.
- Step 3: Handedness check: verifies left vs right mapping (SIG-08).
- Step 4: Pointer range of motion: interaction region bounds.
- Step 5: Practice: pinch click, drag, scroll targets.
- Step 6: Safety briefing: clutch (fist), arm (palm), and kill-switch practice.
- Step 7: Summary and profile persistence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from aileron.interfaces import Hand, HandFeatures, Side

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

MIN_ONBOARDING_FPS = 15.0
MIN_ONBOARDING_WIDTH = 640
MIN_ONBOARDING_HEIGHT = 480
MIN_HAND_CONFIDENCE = 0.70
PRACTICE_PINCH_TARGET = 0.25
MAX_FIST_CURL_THRESHOLD = 0.35


class OnboardingStep(Enum):
    """Sequential phases of the onboarding experience."""

    WELCOME = "welcome"
    CAMERA_CHECK = "camera_check"
    HANDEDNESS_CHECK = "handedness_check"
    RANGE_OF_MOTION = "range_of_motion"
    PRACTICE_PINCH = "practice_pinch"
    SAFETY_BRIEFING = "safety_briefing"
    COMPLETE = "complete"


@dataclass(slots=True)
class OnboardingState:
    """Tracks completion of onboarding milestones."""

    current_step: OnboardingStep = OnboardingStep.WELCOME
    camera_ok: bool = False
    handedness_confirmed: Side | None = None
    pinch_practiced: bool = False
    safety_clutch_practiced: bool = False
    safety_kill_switch_briefed: bool = False
    completed: bool = False


class OnboardingFlow:
    """Manages progression and verification through the onboarding wizard."""

    def __init__(self) -> None:
        self.state = OnboardingState()

    def advance_to(self, step: OnboardingStep) -> None:
        """Advance to target onboarding step."""
        self.state.current_step = step
        if step == OnboardingStep.COMPLETE:
            self.state.completed = True
        logger.info("Onboarding step advanced to: %s", step.value)

    def verify_camera(self, fps: float, width: int, height: int) -> bool:
        """Verify camera stream meets minimum resolution and framerate requirements."""
        if (
            fps >= MIN_ONBOARDING_FPS
            and width >= MIN_ONBOARDING_WIDTH
            and height >= MIN_ONBOARDING_HEIGHT
        ):
            self.state.camera_ok = True
            return True
        self.state.camera_ok = False
        return False

    def verify_handedness(self, visible_hands: Sequence[Hand], requested_side: Side) -> bool:
        """Verify detected hand side matches user's raised hand per SIG-08."""
        matching = [
            h for h in visible_hands if h.side == requested_side and h.score >= MIN_HAND_CONFIDENCE
        ]
        if matching:
            self.state.handedness_confirmed = requested_side
            return True
        return False

    def record_practice_pinch(self, pinch_dist: float) -> bool:
        """Confirm user successfully performed a practice pinch click."""
        if pinch_dist < PRACTICE_PINCH_TARGET:
            self.state.pinch_practiced = True
            return True
        return False

    def record_safety_clutch(self, features: HandFeatures) -> bool:
        """Confirm user performed a practice fist clutch dwell."""
        # Check all fingers curled
        curls = features.curl
        all_curled = all(
            curls.get(f, 1.0) < MAX_FIST_CURL_THRESHOLD
            for f in ["index", "middle", "ring", "pinky"]
        )
        if all_curled:
            self.state.safety_clutch_practiced = True
            return True
        return False

    def acknowledge_kill_switch(self) -> None:
        """Record user acknowledgment of global emergency stop hotkey."""
        self.state.safety_kill_switch_briefed = True
