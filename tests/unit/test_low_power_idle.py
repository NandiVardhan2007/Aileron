"""Unit tests for low-power idle mode (M7).

Verifies:
- CaptureThread releases camera handle when set_idle(True) is invoked.
- CaptureThread re-opens camera when resumed from idle.
- ControlPipeline updates power mode based on SessionState and preview presence.
"""

from unittest.mock import MagicMock

import numpy as np

from aileron.capture import CaptureThread, FakeCapture
from aileron.config import AileronConfig, CameraConfig
from aileron.control import ControlPipeline
from aileron.interfaces import SessionState


def test_capture_thread_idle_release_and_resume() -> None:
    """CaptureThread releases underlying camera handle when idle, reopens on resume."""
    mock_cap = MagicMock(spec=FakeCapture())
    mock_cap.isOpened.return_value = True
    dummy_img = np.zeros((480, 640, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, dummy_img)

    cfg = CameraConfig(device=0, width=640, height=480, fps=30)
    ct = CaptureThread(config=cfg, custom_capture=mock_cap)

    ct.start()
    try:
        # Initial active state
        assert not ct.is_idle

        # Transition to idle -> camera released
        ct.set_idle(True)
        assert ct.is_idle
        assert not ct.is_camera_open

        # Transition to active -> re-opened
        ct.set_idle(False)
        assert not ct.is_idle
    finally:
        ct.stop()


def test_control_pipeline_power_mode_transitions() -> None:
    """ControlPipeline automatically idles camera when DISARMED and preview is off."""
    config = AileronConfig()
    mock_cap_thread = MagicMock(spec=CaptureThread)

    pipeline = ControlPipeline(config=config, capture_thread=mock_cap_thread)
    assert pipeline.session_manager.state == SessionState.DISARMED

    # 1. DISARMED + no preview -> Idle is activated
    is_idle = pipeline.update_power_mode(has_preview=False)
    assert is_idle is True
    mock_cap_thread.set_idle.assert_called_with(True)

    # 2. DISARMED + preview active -> Idle is NOT activated (keep camera running for UI)
    is_idle = pipeline.update_power_mode(has_preview=True)
    assert is_idle is False
    mock_cap_thread.set_idle.assert_called_with(False)

    # 3. Transition to ARMED -> Idle is NOT activated even without preview
    pipeline.session_manager.transition_to(SessionState.ARMED)
    assert pipeline.session_manager.state == SessionState.ARMED
    is_idle = pipeline.update_power_mode(has_preview=False)
    assert is_idle is False
    mock_cap_thread.set_idle.assert_called_with(False)
