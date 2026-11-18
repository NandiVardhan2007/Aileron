"""Unit tests for Linux uinput backend with mock devices (M7)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    ButtonUp,
    MoveBy,
    Pad,
    PadButton,
    Scroll,
    Trigger,
    Zoom,
)
from aileron.output.linux import (
    ABS_X,
    ABS_Y,
    ABS_Z,
    BTN_LEFT,
    BTN_SOUTH,
    EV_ABS,
    EV_KEY,
    EV_REL,
    REL_WHEEL,
    REL_X,
    REL_Y,
    LinuxUInputBackend,
)


def test_linux_backend_platform_check() -> None:
    """Linux backend rejects instantiation/open on non-Linux platforms."""
    backend = LinuxUInputBackend()
    if sys.platform != "linux":
        with pytest.raises(RuntimeError, match="LinuxUInputBackend is only supported on Linux"):
            backend.open()


def test_linux_backend_missing_evdev_package() -> None:
    """Linux backend reports informative error when evdev is missing."""
    backend = LinuxUInputBackend()
    with (
        patch("sys.platform", "linux"),
        patch.dict(sys.modules, {"evdev": None}),
        pytest.raises(RuntimeError, match="requires the 'evdev' Python package"),
    ):
        backend.open()


def test_linux_backend_mock_actuation() -> None:
    """Linux backend translates intents to uinput write/syn events."""
    mock_dev = MagicMock()
    backend = LinuxUInputBackend(uinput_device=mock_dev)
    backend.open()
    assert backend.is_open

    # 1. Motion
    backend.apply([MoveBy(dx=15, dy=-10)])
    mock_dev.write.assert_any_call(EV_REL, REL_X, 15)
    mock_dev.write.assert_any_call(EV_REL, REL_Y, -10)

    # 2. Button Down/Up
    backend.apply([ButtonDown(button=Button.LEFT)])
    mock_dev.write.assert_any_call(EV_KEY, BTN_LEFT, 1)
    assert "mouse_left" in backend.held()

    backend.apply([ButtonUp(button=Button.LEFT)])
    mock_dev.write.assert_any_call(EV_KEY, BTN_LEFT, 0)
    assert "mouse_left" not in backend.held()

    # 3. Gamepad Axis & Trigger
    backend.apply(
        [
            Axis(name="lx", value=0.5),
            Trigger(name="lt", value=0.8),
            Pad(button=PadButton.A, down=True),
        ]
    )
    mock_dev.write.assert_any_call(EV_ABS, ABS_X, int(0.5 * 32767))
    mock_dev.write.assert_any_call(EV_ABS, ABS_Z, int(0.8 * 255))
    mock_dev.write.assert_any_call(EV_KEY, BTN_SOUTH, 1)
    assert "pad_a" in backend.held()

    # 4. Scroll & Zoom
    backend.apply([Scroll(dx=0.0, dy=3.0), Zoom(steps=2)])
    mock_dev.write.assert_any_call(EV_REL, REL_WHEEL, 3)

    # 5. ReleaseAll
    backend.release_all()
    assert backend.held() == frozenset()
    mock_dev.write.assert_any_call(EV_ABS, ABS_X, 0)
    mock_dev.write.assert_any_call(EV_ABS, ABS_Y, 0)
    mock_dev.write.assert_any_call(EV_ABS, ABS_Z, 0)

    backend.close()
    assert not backend.is_open
