"""Dwell gesture detectors: clutch, resume, arm, and mode toggle (M3).

Implements G-01, G-09, G-10, G-11, G-12, and SIGNAL_PROCESSING §12:
- Clutch (fist dwell, default 400 ms)
- Resume (open palm dwell while in STANDBY, default 400 ms)
- Arm (open palm dwell while in DISARMED, default 800 ms)
- Mode toggle (shaka dwell, default 800 ms)
- Progress tracking 0.0..1.0 for HUD dwell rings
- Grace period handling (dwell_grace_ms = 100 ms) to survive tracker flickers
"""

from collections.abc import Sequence
from enum import Enum

from aileron.config import FingersConfig, SessionConfig, TrackingConfig
from aileron.interfaces import GestureEvent, GestureKind, HandFeatures, SessionState

MIN_FIST_PINCH = 0.40
MIN_PALM_FACING_Z = 0.5


class DwellGestureKind(Enum):
    """Supported dwell gesture types."""

    CLUTCH = "clutch"
    RESUME = "resume"
    ARM = "arm"
    MODE_TOGGLE = "mode_toggle"


class DwellTimer:
    """Tracks a single dwell gesture progress with grace period tolerance."""

    def __init__(self, target_ms: int, grace_ms: int = 100) -> None:
        self.target_ms = target_ms
        self.grace_ms = grace_ms
        self._accum_ms: float = 0.0
        self._last_t_ns: int = 0
        self._grace_accum_ms: float = 0.0
        self._active: bool = False
        self._fired: bool = False

    @property
    def progress(self) -> float:
        """Normalized dwell progress 0.0 .. 1.0."""
        if not self._active or self.target_ms <= 0:
            return 0.0
        return min(1.0, self._accum_ms / self.target_ms)

    def reset(self) -> None:
        """Reset dwell timer."""
        self._accum_ms = 0.0
        self._last_t_ns = 0
        self._grace_accum_ms = 0.0
        self._active = False
        self._fired = False

    def update(self, pose_matched: bool, t_ns: int) -> bool:
        """Update timer. Returns True on the exact tick when dwell target is reached."""
        if self._fired:
            if not pose_matched:
                self.reset()
            return False

        if not self._active:
            if pose_matched:
                self._active = True
                self._accum_ms = 0.0
                self._grace_accum_ms = 0.0
                self._last_t_ns = t_ns
            return False

        # Active
        dt_ms = (t_ns - self._last_t_ns) / 1_000_000.0
        self._last_t_ns = t_ns

        if pose_matched:
            self._grace_accum_ms = 0.0
            self._accum_ms += dt_ms
            if self._accum_ms >= self.target_ms:
                self._fired = True
                return True
        else:
            # Pose interrupted; check grace period tolerance
            self._grace_accum_ms += dt_ms
            if self._grace_accum_ms > self.grace_ms:
                self.reset()

        return False


class DwellGestureDetector:
    """Detects dwell gestures and supplies progress values for HUD indicators."""

    name: str = "dwell"

    def __init__(
        self,
        session_cfg: SessionConfig,
        fingers_cfg: FingersConfig,
        tracking_cfg: TrackingConfig,
    ) -> None:
        self.session_cfg = session_cfg
        self.fingers_cfg = fingers_cfg
        self.tracking_cfg = tracking_cfg

        self.clutch_timer = DwellTimer(session_cfg.clutch_ms, tracking_cfg.dwell_grace_ms)
        self.resume_timer = DwellTimer(session_cfg.resume_ms, tracking_cfg.dwell_grace_ms)
        self.arm_timer = DwellTimer(session_cfg.arm_ms, tracking_cfg.dwell_grace_ms)
        self.mode_timer = DwellTimer(session_cfg.mode_ms, tracking_cfg.dwell_grace_ms)

        self.progress_dict: dict[str, float] = {}

    def reset(self) -> None:
        """Reset all dwell timers."""
        self.clutch_timer.reset()
        self.resume_timer.reset()
        self.arm_timer.reset()
        self.mode_timer.reset()
        self.progress_dict = {}

    def is_fist(self, h: HandFeatures) -> bool:
        """Fist: all 4 fingers curled (curl < ext_off), pinch > 0.5."""
        curls = h.curl
        for f in ("index", "middle", "ring", "pinky"):
            if curls.get(f, 1.0) > self.fingers_cfg.ext_off:
                return False
        # Pinch ratio must not be closed pinch
        return h.pinch.get("index", 1.0) > MIN_FIST_PINCH

    def is_open_palm(self, h: HandFeatures) -> bool:
        """Open palm: all fingers extended, palm normal facing camera (z >= 0.5)."""
        curls = h.curl
        for f in ("thumb", "index", "middle", "ring", "pinky"):
            if curls.get(f, 0.0) < self.fingers_cfg.ext_on:
                return False
        # Palm facing camera: z component >= MIN_PALM_FACING_Z
        return float(h.palm_normal[2]) >= MIN_PALM_FACING_Z

    def is_shaka(self, h: HandFeatures) -> bool:
        """Shaka: thumb & pinky extended, index, middle, ring curled."""
        curls = h.curl
        if curls.get("thumb", 0.0) < self.fingers_cfg.ext_on:
            return False
        if curls.get("pinky", 0.0) < self.fingers_cfg.ext_on:
            return False
        for f in ("index", "middle", "ring"):
            if curls.get(f, 1.0) > self.fingers_cfg.ext_off:
                return False
        return True

    def update_with_state(
        self,
        feats: Sequence[HandFeatures],
        t_ns: int,
        session_state: SessionState,
    ) -> Sequence[GestureEvent]:
        """Update dwell state machines taking active SessionState into account."""
        events: list[GestureEvent] = []
        self.progress_dict = {}

        if not feats or not feats[0].valid:
            # Lost hand
            self.clutch_timer.update(False, t_ns)
            self.resume_timer.update(False, t_ns)
            self.arm_timer.update(False, t_ns)
            self.mode_timer.update(False, t_ns)
            return ()

        h = feats[0]
        matched_fist = self.is_fist(h)
        matched_palm = self.is_open_palm(h)
        matched_shaka = self.is_shaka(h)

        # 1. Clutch: only active when ARMED
        clutch_pose = matched_fist and (session_state == SessionState.ARMED)
        if self.clutch_timer.update(clutch_pose, t_ns):
            events.append(GestureEvent(kind=GestureKind.CLUTCH, t_ns=t_ns, side=h.side))
        if self.clutch_timer.progress > 0.0:
            self.progress_dict["clutch"] = self.clutch_timer.progress

        # 2. Resume: only active when STANDBY
        resume_pose = matched_palm and (session_state == SessionState.STANDBY)
        if self.resume_timer.update(resume_pose, t_ns):
            events.append(GestureEvent(kind=GestureKind.RESUME, t_ns=t_ns, side=h.side))
        if self.resume_timer.progress > 0.0:
            self.progress_dict["resume"] = self.resume_timer.progress

        # 3. Arm: only active when DISARMED
        arm_pose = matched_palm and (session_state == SessionState.DISARMED)
        if self.arm_timer.update(arm_pose, t_ns):
            events.append(GestureEvent(kind=GestureKind.RESUME, t_ns=t_ns, side=h.side))
        if self.arm_timer.progress > 0.0:
            self.progress_dict["arm"] = self.arm_timer.progress

        # 4. Mode toggle: Shaka pose (available in ARMED)
        mode_pose = matched_shaka and (session_state == SessionState.ARMED)
        if self.mode_timer.update(mode_pose, t_ns):
            events.append(GestureEvent(kind=GestureKind.MODE_TOGGLE, t_ns=t_ns, side=h.side))
        if self.mode_timer.progress > 0.0:
            self.progress_dict["mode_toggle"] = self.mode_timer.progress

        return tuple(events)

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]:
        """Conforms to GestureDetector protocol default update (assumes ARMED)."""
        return self.update_with_state(feats, t_ns, SessionState.ARMED)
