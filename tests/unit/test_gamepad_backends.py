"""Unit tests for Gamepad backends (NullBackend, KeyboardPwmGamepad, VGamepadBackend) (M5).

Verifies:
- NullBackend gamepad capability and held input tracking
- KeyboardPwmGamepad analog-to-key translation
- VGamepadBackend lazy import and driver-missing error handling
- VGamepadBackend mock test of axis and button injection
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from aileron.interfaces import (
    Axis,
    Pad,
    PadButton,
    Trigger,
)
from aileron.output.gamepad import KeyboardPwmGamepad, VGamepadBackend
from aileron.output.null import NullBackend


def test_null_backend_gamepad_handling() -> None:
    """NullBackend accepts and records Axis, Trigger, and Pad intents."""
    nb = NullBackend()
    nb.open()

    nb.apply(
        [
            Axis(name="lx", value=0.5),
            Trigger(name="rt", value=0.75),
            Pad(button=PadButton.RB, down=True),
        ]
    )

    held = nb.held()
    assert len(held) > 0

    # release_all empties held set
    nb.release_all()
    assert nb.held() == frozenset()
    nb.close()


def test_keyboard_pwm_gamepad_translation() -> None:
    """KeyboardPwmGamepad maps analog stick and trigger values to keyboard keys."""
    pwm = KeyboardPwmGamepad()
    pwm.open()

    # Steer Left -> 'a'
    pwm.apply([Axis(name="lx", value=-0.6)])
    assert "a" in pwm.held()
    assert "d" not in pwm.held()

    # Steer Right -> 'd'
    pwm.apply([Axis(name="lx", value=0.6)])
    assert "d" in pwm.held()
    assert "a" not in pwm.held()

    # Throttle -> 'w'
    pwm.apply([Trigger(name="rt", value=0.8)])
    assert "w" in pwm.held()

    # Brake -> 's'
    pwm.apply([Trigger(name="lt", value=0.5)])
    assert "s" in pwm.held()

    # Neutralize
    pwm.release_all()
    assert pwm.held() == frozenset()
    pwm.close()


def test_vgamepad_driver_missing_graceful_error() -> None:
    """VGamepadBackend raises clear RuntimeError when driver or vgamepad is missing."""
    backend = VGamepadBackend()

    with (
        patch.dict(sys.modules, {"vgamepad": None}),
        pytest.raises(RuntimeError, match="ViGEmBus / vgamepad driver is unavailable"),
    ):
        backend.open()


def test_vgamepad_mocked_actuation() -> None:
    """VGamepadBackend translates Axis, Trigger, and Pad to native vgamepad calls."""
    backend = VGamepadBackend()

    mock_vg = MagicMock()
    mock_pad_instance = MagicMock()
    mock_vg.VX360Gamepad.return_value = mock_pad_instance

    with patch.dict(sys.modules, {"vgamepad": mock_vg}):
        backend.open()
        assert backend.is_open

        # Apply intents
        backend.apply(
            [
                Axis(name="lx", value=0.45),
                Trigger(name="rt", value=0.80),
                Trigger(name="lt", value=0.20),
                Pad(button=PadButton.RB, down=True),
            ]
        )

        # Assert correct methods were called on virtual gamepad
        mock_pad_instance.left_joystick_float.assert_called_with(
            x_value_float=0.45, y_value_float=0.0
        )
        mock_pad_instance.right_trigger_float.assert_called_with(value_float=0.80)
        mock_pad_instance.left_trigger_float.assert_called_with(value_float=0.20)
        mock_pad_instance.update.assert_called()

        # Release all
        backend.release_all()
        mock_pad_instance.reset.assert_called()
        backend.close()
