"""Control pipeline and fail-closed execution loop (M4).

Follows ARCHITECTURE §2-3 and SAFETY §1, §4, §8:
- Fixed-rate tick stepping through feature extraction, gestures, gating, and actuation.
- Independent watchdog and camera-stall guards.
- Fail-closed exception boundary: any unhandled error triggers immediate FAULT state,
  releases all held inputs, and logs blackbox diagnostic data.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from aileron.config import AileronConfig
from aileron.features.extraction import extract_features
from aileron.gestures.engine import GestureEngine
from aileron.interfaces import GestureOutput, HandFeatures, HandFrame, Intent, SessionState
from aileron.modes.manager import ModeManager
from aileron.modes.session import SessionStateManager
from aileron.output.base import OutputBackend
from aileron.output.null import NullBackend
from aileron.safety.blackbox import BlackBoxRecorder
from aileron.safety.gate import SafetyGate
from aileron.safety.kill_switch import KillSwitchListener
from aileron.safety.watchdog import CameraStallGuard, Watchdog

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class StepResult:
    """Telemetry and outcome of a single control pipeline step."""

    t_ns: int
    state: SessionState
    output: GestureOutput | None
    intents: tuple[Intent, ...]
    is_fault: bool = False
    fault_reason: str | None = None


class ControlPipeline:
    """Central orchestrator coordinating vision, gestures, safety, and output."""

    def __init__(
        self,
        config: AileronConfig,
        backend: OutputBackend | None = None,
        safety_gate: SafetyGate | None = None,
        session_manager: SessionStateManager | None = None,
        mode_manager: ModeManager | None = None,
        gesture_engine: GestureEngine | None = None,
        blackbox: BlackBoxRecorder | None = None,
        start_watchdog: bool = False,
    ) -> None:
        self.config = config
        self.backend = backend or NullBackend()
        self.gate = safety_gate or SafetyGate(
            click_cfg=config.click,
            initial_state=SessionState.DISARMED,
        )
        self.session_manager = session_manager or SessionStateManager(
            safety_gate=self.gate,
            start_armed=config.session.start_armed,
        )
        self.mode_manager = mode_manager or ModeManager()
        self.engine = gesture_engine or GestureEngine(
            config=config,
            session_manager=self.session_manager,
            mode_manager=self.mode_manager,
        )
        self.blackbox = blackbox or BlackBoxRecorder(
            capacity=600,
            enabled=True,
        )
        self.camera_guard = CameraStallGuard(
            timeout_s=config.tracking.camera_stall_timeout_s
            if hasattr(config.tracking, "camera_stall_timeout_s")
            else 0.500
        )

        # Watchdog setup
        self.watchdog = Watchdog(
            backend=self.backend,
            on_stall=self._handle_watchdog_stall,
            stall_timeout_s=0.250,
            check_interval_s=0.050,
        )
        if start_watchdog:
            self.watchdog.start()

        self.kill_switch: KillSwitchListener | None = None

    def _handle_watchdog_stall(self, reason: str) -> None:
        """Invoked when watchdog detects a control loop stall."""
        logger.critical("ControlPipeline: Watchdog stall fired: %s", reason)
        self.session_manager.trigger_fault(reason)
        try:
            self.backend.release_all()
        except Exception:
            logger.exception("Error releasing inputs during watchdog stall")

    def attach_kill_switch(self, listener: KillSwitchListener) -> None:
        """Attach an active OS kill-switch listener."""
        self.kill_switch = listener

    def step(
        self,
        frame: HandFrame | None,
        now_ns: int | None = None,
    ) -> StepResult:
        """Execute one tick of the control pipeline (fail-closed per SAFE-08)."""
        t_now = time.monotonic_ns() if now_ns is None else now_ns

        # 1. Update watchdogs and heartbeat
        self.watchdog.heartbeat(t_now)
        self.gate.heartbeat(t_now)

        # 2. Check camera stall guard
        if frame is not None and frame.hands:
            self.camera_guard.record_frame(t_now)

        active_frame = frame
        if self.camera_guard.is_stalled(t_now):
            # Camera feed stalled: treat as hand lost (SAFE-02, SAFE-04)
            active_frame = HandFrame(t_capture_ns=t_now, t_infer_done_ns=t_now, seq=0, hands=())

        if active_frame is None:
            active_frame = HandFrame(t_capture_ns=t_now, t_infer_done_ns=t_now, seq=0, hands=())

        # 3. Fail-closed processing block
        try:
            # Extract features for visible hands
            feats: list[HandFeatures] = [
                extract_features(h, self.config.tracking, self.config.fingers)
                for h in active_frame.hands
            ]

            # Run gesture engine
            gesture_output, candidate_intents = self.engine.process(active_frame, feats)

            # Filter candidates through SafetyGate
            approved_intents = self.gate.filter(candidate_intents, t_now)

            # Apply to output backend
            self.backend.apply(approved_intents)

            # Record in blackbox circular buffer
            self.blackbox.record(active_frame, approved_intents)

            return StepResult(
                t_ns=t_now,
                state=self.session_manager.state,
                output=gesture_output,
                intents=tuple(approved_intents),
                is_fault=False,
            )

        except Exception as exc:
            # SAFE-08: Fail-closed boundary
            logger.exception("ControlPipeline encountered exception: %s", exc)
            fault_reason = f"Pipeline exception: {exc}"

            # Immediately trigger FAULT state and neutralize
            releases = self.session_manager.trigger_fault(fault_reason)
            try:
                self.backend.release_all()
            except Exception:
                logger.exception("Error during fail-closed backend.release_all()")

            # Attempt to dump blackbox buffer
            try:
                dump_path = Path(".aileron_fault_blackbox.jsonl")
                self.blackbox.dump_to_file(dump_path, reason=fault_reason)
            except Exception:
                logger.exception("Error saving blackbox dump on fault")

            return StepResult(
                t_ns=t_now,
                state=SessionState.FAULT,
                output=None,
                intents=tuple(releases),
                is_fault=True,
                fault_reason=fault_reason,
            )

    def shutdown(self) -> None:
        """Orderly shutdown releasing all held inputs and stopping background threads."""
        logger.info("ControlPipeline shutting down...")
        self.watchdog.stop()
        if self.kill_switch is not None:
            self.kill_switch.stop()

        self.session_manager.transition_to(SessionState.DISARMED, reason="Pipeline shutdown")
        try:
            self.backend.release_all()
            self.backend.close()
        except Exception:
            logger.exception("Error closing backend on shutdown")
