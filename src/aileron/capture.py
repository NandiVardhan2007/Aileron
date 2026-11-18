"""Camera capture thread with single-slot latest-frame buffer and mirroring."""

import threading
import time
from collections.abc import Callable

import cv2
import numpy as np

from aileron.config import CameraConfig
from aileron.interfaces import Frame

MIN_SLEEP_SEC = 0.001
RECONNECT_SLEEP_SEC = 0.05


class CaptureThread:
    """Thread responsible for grabbing camera frames at target rate into a 1-slot buffer."""

    def __init__(
        self,
        config: CameraConfig,
        custom_capture: object | None = None,
    ) -> None:
        self.config = config
        self._custom_capture = custom_capture
        self._cap: cv2.VideoCapture | object | None = None
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._lock = threading.RLock()
        self._has_frame = threading.Condition(self._lock)
        self._latest_frame: Frame | None = None
        self._seq: int = 0
        self._error: Exception | None = None
        self._idle: bool = False

    @property
    def is_idle(self) -> bool:
        """Whether capture thread is in low-power idle mode."""
        with self._lock:
            return self._idle

    @property
    def is_camera_open(self) -> bool:
        """Whether physical camera handle is currently acquired."""
        with self._lock:
            return self._cap is not None

    def set_idle(self, idle: bool) -> None:
        """Toggle low-power idle mode (releases camera hardware when idle)."""
        with self._lock:
            if self._idle == idle:
                return
            self._idle = idle
            if idle:
                self._release_camera()
            self._has_frame.notify_all()

    @property
    def latest_error(self) -> Exception | None:
        """Last capture exception if camera failed."""
        with self._lock:
            return self._error

    def start(self) -> None:
        """Start the background capture loop."""
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="aileron-capture", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop capture loop and release camera resource."""
        self._running = False
        with self._has_frame:
            self._has_frame.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._release_camera()

    def get_latest_frame(self, timeout_s: float | None = 0.1) -> Frame | None:
        """Retrieve the newest frame from the single-slot buffer, clearing it."""
        with self._has_frame:
            if self._latest_frame is None and timeout_s is not None and timeout_s > 0:
                self._has_frame.wait(timeout=timeout_s)
            frame = self._latest_frame
            self._latest_frame = None
            return frame

    def peek_latest_frame(self) -> Frame | None:
        """Inspect the newest frame without clearing the single-slot buffer."""
        with self._lock:
            return self._latest_frame

    def _open_camera(self) -> None:
        if self._custom_capture is not None:
            self._cap = self._custom_capture
            return

        cap = cv2.VideoCapture(self.config.device)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.config.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.config.height))
        cap.set(cv2.CAP_PROP_FPS, float(self.config.fps))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, float(self.config.buffer_size))

        if not cap.isOpened():
            raise RuntimeError(f"Unable to open camera device index {self.config.device}")
        self._cap = cap

    def _release_camera(self) -> None:
        if self._cap is not None:
            release_fn = getattr(self._cap, "release", None)
            if callable(release_fn):
                release_fn()
            self._cap = None

    def _run(self) -> None:
        try:
            self._open_camera()
        except Exception as e:
            with self._lock:
                self._error = e
            return

        target_interval = 1.0 / max(1, self.config.fps)

        while self._running:
            with self._lock:
                idle = self._idle

            if idle:
                with self._has_frame:
                    self._has_frame.wait(timeout=0.05)
                continue

            if self._cap is None:
                try:
                    self._open_camera()
                except Exception as e:
                    with self._lock:
                        self._error = e
                    time.sleep(RECONNECT_SLEEP_SEC)
                    continue

            t0 = time.monotonic()

            read_fn: Callable[[], tuple[bool, np.ndarray | None]] | None = getattr(
                self._cap, "read", None
            )
            if not callable(read_fn):
                break
            ret, frame = read_fn()
            t_capture_ns = time.monotonic_ns()

            if not ret or frame is None:
                with self._lock:
                    self._error = RuntimeError("Camera frame read failed or device disconnected")
                time.sleep(RECONNECT_SLEEP_SEC)
                continue

            # Mirror once at capture (ADR-011)
            if self.config.mirror:
                frame = cv2.flip(frame, 1)

            with self._has_frame:
                self._seq += 1
                self._latest_frame = Frame(
                    t_capture_ns=t_capture_ns,
                    seq=self._seq,
                    image=frame,
                )
                self._has_frame.notify_all()

            elapsed = time.monotonic() - t0
            sleep_time = target_interval - elapsed
            if sleep_time > MIN_SLEEP_SEC:
                time.sleep(sleep_time)


class FakeCapture:
    """Mock capture source for headless tests and simulated video streams."""

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 60) -> None:
        self.width = width
        self.height = height
        self.fps = fps
        self._is_opened = True

    def isOpened(self) -> bool:  # noqa: N802
        return self._is_opened

    def read(self) -> tuple[bool, np.ndarray]:
        img = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        return True, img

    def release(self) -> None:
        self._is_opened = False

    def set(self, prop: int, val: float) -> bool:
        return True
