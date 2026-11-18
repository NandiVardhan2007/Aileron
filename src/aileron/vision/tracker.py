"""MediaPipe Tasks HandLandmarker tracker running in LIVE_STREAM async mode."""

import os
import threading
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    HandLandmarkerResult,
    RunningMode,
)

from aileron.config import TrackingConfig
from aileron.interfaces import Frame, Hand, HandFrame
from aileron.vision.hands import parse_hand

DEFAULT_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
DEFAULT_MODEL_PATH = Path("models/hand_landmarker.task")
MIN_TASK_MODEL_BYTES = 100_000
MAX_PENDING_INFERENCES = 10


def ensure_model_file(model_path: Path | str | None = None) -> Path:
    """Ensure the MediaPipe hand landmarker task file is present, downloading if necessary."""
    env_str = os.environ.get("AILERON_MODEL_PATH")
    target = model_path if model_path is not None else (env_str if env_str else DEFAULT_MODEL_PATH)
    path = Path(target)
    if path.is_file() and path.stat().st_size > MIN_TASK_MODEL_BYTES:
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    urllib.request.urlretrieve(DEFAULT_MODEL_URL, temp_path)
    temp_path.replace(path)
    return path


class HandTracker:
    """MediaPipe Tasks HandLandmarker wrapper with LIVE_STREAM callback."""

    def __init__(
        self,
        config: TrackingConfig,
        model_path: Path | str | None = None,
        is_mirrored: bool = True,
        auto_download: bool = True,
    ) -> None:
        self.config = config
        self.is_mirrored = is_mirrored
        self._lock = threading.Lock()
        self._has_frame = threading.Condition(self._lock)
        self._latest_hand_frame: HandFrame | None = None
        self._pending_frames: dict[int, Frame] = {}
        self._landmarker: HandLandmarker | None = None

        if auto_download:
            resolved_path = ensure_model_file(model_path)
        else:
            resolved_path = Path(model_path or DEFAULT_MODEL_PATH)
            if not resolved_path.is_file():
                raise FileNotFoundError(f"MediaPipe task model not found at {resolved_path}")

        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(resolved_path)),
            running_mode=RunningMode.LIVE_STREAM,
            num_hands=self.config.num_hands,
            min_hand_detection_confidence=self.config.min_detection_conf,
            min_hand_presence_confidence=self.config.min_presence_conf,
            min_tracking_confidence=self.config.min_tracking_conf,
            result_callback=self._on_result,
        )
        self._landmarker = HandLandmarker.create_from_options(options)

    def _on_result(
        self,
        result: HandLandmarkerResult,
        output_image: mp.Image,
        timestamp_ms: int,
    ) -> None:
        t_infer_done_ns = time.monotonic_ns()
        with self._lock:
            frame = self._pending_frames.pop(timestamp_ms, None)
            t_capture_ns = frame.t_capture_ns if frame else t_infer_done_ns
            seq = frame.seq if frame else 0

            hands: list[Hand] = []
            if result.handedness and result.hand_landmarks:
                for idx, categories in enumerate(result.handedness):
                    if idx >= len(result.hand_landmarks):
                        break
                    cat = categories[0]
                    score = float(cat.score)
                    if score < self.config.min_hand_conf:
                        continue

                    lm_pts = result.hand_landmarks[idx]
                    world_pts = (
                        result.hand_world_landmarks[idx]
                        if result.hand_world_landmarks and idx < len(result.hand_world_landmarks)
                        else []
                    )
                    hand = parse_hand(
                        category_label=cat.category_name,
                        score=score,
                        landmarks_list=lm_pts,
                        world_landmarks_list=world_pts,
                        is_mirrored=self.is_mirrored,
                    )
                    hands.append(hand)

            self._latest_hand_frame = HandFrame(
                t_capture_ns=t_capture_ns,
                t_infer_done_ns=t_infer_done_ns,
                seq=seq,
                hands=tuple(hands),
            )
            self._has_frame.notify_all()

    def process_frame(self, frame: Frame) -> None:
        """Send a frame asynchronously to the MediaPipe HandLandmarker."""
        if self._landmarker is None:
            raise RuntimeError("HandTracker is closed")

        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int(frame.t_capture_ns // 1_000_000)

        with self._lock:
            # Prevent map from unbounded growth if callbacks stall
            if len(self._pending_frames) > MAX_PENDING_INFERENCES:
                self._pending_frames.clear()
            self._pending_frames[timestamp_ms] = frame

        self._landmarker.detect_async(mp_image, timestamp_ms)

    def get_latest_hand_frame(self, timeout_s: float | None = 0.05) -> HandFrame | None:
        """Fetch the newest completed HandFrame from the inference mailbox."""
        with self._has_frame:
            if self._latest_hand_frame is None and timeout_s is not None and timeout_s > 0:
                self._has_frame.wait(timeout=timeout_s)
            frame = self._latest_hand_frame
            self._latest_hand_frame = None
            return frame

    def close(self) -> None:
        """Release MediaPipe landmarker resources."""
        with self._lock:
            if self._landmarker is not None:
                self._landmarker.close()
                self._landmarker = None
            self._pending_frames.clear()
            self._has_frame.notify_all()
