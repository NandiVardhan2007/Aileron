"""Unit tests for macOS Quartz backend with mock CoreGraphics (M7)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from aileron.interfaces import (
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    Key,
    MoveTo,
    Scroll,
    Zoom,
)
from aileron.output.macos import (
    CG_EVENT_LEFT_MOUSE_DOWN,
    CG_EVENT_LEFT_MOUSE_UP,
    CG_EVENT_MOUSE_MOVED,
    MacosQuartzBackend,
)


def test_macos_backend_platform_check() -> None:
    """macOS backend rejects instantiation/open on non-darwin platforms."""
    backend = MacosQuartzBackend()
    if sys.platform != "darwin":
        with pytest.raises(RuntimeError, match="MacosQuartzBackend is only supported on macOS"):
            backend.open()


def test_macos_backend_missing_quartz_package() -> None:
    """macOS backend reports informative error when pyobjc-framework-Quartz is missing."""
    backend = MacosQuartzBackend()
    with (
        patch("sys.platform", "darwin"),
        patch.dict(sys.modules, {"Quartz": None}),
        pytest.raises(RuntimeError, match="requires the 'pyobjc-framework-Quartz' package"),
    ):
        backend.open()


def test_macos_backend_mock_actuation() -> None:
    """macOS backend posts mouse, scroll, and key events via CoreGraphics."""
    mock_cg = MagicMock()
    mock_cg.CGEventCreateMouseEvent.return_value = "mock_mouse_event"
    mock_cg.CGEventCreateScrollWheelEvent2.return_value = "mock_scroll_event"
    mock_cg.CGEventCreateKeyboardEvent.return_value = "mock_key_event"

    backend = MacosQuartzBackend(cg_module=mock_cg)
    backend.open()
    assert backend.is_open

    # 1. MoveTo
    backend.apply([MoveTo(x=400, y=300)])
    mock_cg.CGEventCreateMouseEvent.assert_called_with(
        None, CG_EVENT_MOUSE_MOVED, (400.0, 300.0), 0
    )
    mock_cg.CGEventPost.assert_called_with(0, "mock_mouse_event")

    # 2. Button Down/Up
    backend.apply([ButtonDown(button=Button.LEFT)])
    mock_cg.CGEventCreateMouseEvent.assert_called_with(
        None, CG_EVENT_LEFT_MOUSE_DOWN, (400.0, 300.0), 0
    )
    assert "mouse_left" in backend.held()

    backend.apply([ButtonUp(button=Button.LEFT)])
    mock_cg.CGEventCreateMouseEvent.assert_called_with(
        None, CG_EVENT_LEFT_MOUSE_UP, (400.0, 300.0), 0
    )
    assert "mouse_left" not in backend.held()

    # 3. Click
    backend.apply([Click(button=Button.LEFT, count=1)])
    assert "mouse_left" not in backend.held()

    # 4. Scroll & Zoom
    backend.apply([Scroll(dx=0.0, dy=-2.0), Zoom(steps=1)])
    mock_cg.CGEventCreateScrollWheelEvent2.assert_called()

    # 5. Key chord
    backend.apply([Key(chord="ctrl", down=True)])
    assert "key_ctrl" in backend.held()

    # 6. ReleaseAll
    backend.release_all()
    assert backend.held() == frozenset()

    backend.close()
    assert not backend.is_open
