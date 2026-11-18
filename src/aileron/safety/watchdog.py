"""Watchdog thread and camera-stall guard ensuring fail-closed operation (M4).

Follows SAFETY §4:
- Control loop writes heartbeat timestamp every tick.
- Watchdog checks heartbeat at regular intervals (50 ms); if stale > 250 ms:
  calls backend.release_all() and triggers FAULT state.
- Camera-stall guard checks frame arrival; if no frames for > 500 ms:
  triggers hand lost / failsafe neutralization.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aileron.output.base import OutputBackend

logger = logging.getLogger(__name__)

DEFAULT_STALL_TIMEOUT_S = 0.250  # 250 ms (SAFETY §4)
DEFAULT_CHECK_INTERVAL_S = 0.050  # 50 ms (SAFETY §4)
DEFAULT_CAMERA_STALL_TIMEOUT_S = 0.500  # 500 ms (SAFETY §4)
ONE_SEC_NS = 1_000_000_000


class Watchdog:
    """Independent background watchdog monitoring control-loop heartbeat (SAFE-04)."""

    def __init__(
        self,
        backend: OutputBackend,
        on_stall: Callable[[str], None] | None = None,
        stall_timeout_s: float = DEFAULT_STALL_TIMEOUT_S,
        check_interval_s: float = DEFAULT_CHECK_INTERVAL_S,
    ) -> None:
        self._backend = backend
        self._on_stall = on_stall
        self._stall_timeout_s = stall_timeout_s
        self._check_interval_s = check_interval_s

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._last_heartbeat_ns: int = time.monotonic_ns()
        self._stalled = False
        self._stall_count = 0

    @property
    def is_stalled(self) -> bool:
        """Whether the watchdog has detected a heartbeat stall."""
        with self._lock:
            return self._stalled

    @property
    def stall_count(self) -> int:
        """Total number of times a stall has fired."""
        with self._lock:
            return self._stall_count

    def heartbeat(self, now_ns: int | None = None) -> None:
        """Record heartbeat from control loop."""
        ts = time.monotonic_ns() if now_ns is None else now_ns
        with self._lock:
            self._last_heartbeat_ns = ts
            self._stalled = False

    def check_once(self, now_ns: int | None = None) -> bool:
        """Perform a single stall check. Returns True if a stall occurred."""
        ts = time.monotonic_ns() if now_ns is None else now_ns
        with self._lock:
            elapsed_s = (ts - self._last_heartbeat_ns) / ONE_SEC_NS
            is_overdue = elapsed_s > self._stall_timeout_s
            if is_overdue and not self._stalled:
                self._stalled = True
                self._stall_count += 1
                logger.critical(
                    "Watchdog: Control loop stalled for %.3f s (> %.3f s)! Neutralizing.",
                    elapsed_s,
                    self._stall_timeout_s,
                )
                self._execute_failsafe(f"Watchdog stall: elapsed {elapsed_s:.3f}s")
                return True
        return False

    def _execute_failsafe(self, reason: str) -> None:
        """Neutralize backend and notify stall handler."""
        try:
            self._backend.release_all()
        except Exception:
            logger.exception("Watchdog: Error executing backend.release_all()")

        if self._on_stall is not None:
            try:
                self._on_stall(reason)
            except Exception:
                logger.exception("Watchdog: Error executing on_stall callback")

    def _run(self) -> None:
        """Watchdog loop running on dedicated background thread."""
        logger.debug("Watchdog thread started.")
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(timeout=self._check_interval_s)
        logger.debug("Watchdog thread stopped.")

    def start(self) -> None:
        """Start the watchdog background thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._last_heartbeat_ns = time.monotonic_ns()
            self._stalled = False
            self._thread = threading.Thread(
                target=self._run,
                name="AileronWatchdogThread",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_s: float = 1.0) -> None:
        """Stop the watchdog background thread."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout_s)
            self._thread = None


class CameraStallGuard:
    """Monitors camera frame arrivals to detect capture thread stalls (SAFE-04)."""

    def __init__(self, timeout_s: float = DEFAULT_CAMERA_STALL_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s
        self._lock = threading.Lock()
        self._last_frame_ns: int = time.monotonic_ns()

    def record_frame(self, now_ns: int | None = None) -> None:
        """Record arrival of a new video / landmark frame."""
        ts = time.monotonic_ns() if now_ns is None else now_ns
        with self._lock:
            self._last_frame_ns = ts

    def is_stalled(self, now_ns: int | None = None) -> bool:
        """Check if camera feed has stalled (> timeout_s without frames)."""
        ts = time.monotonic_ns() if now_ns is None else now_ns
        with self._lock:
            elapsed_s = (ts - self._last_frame_ns) / ONE_SEC_NS
            return elapsed_s > self.timeout_s
