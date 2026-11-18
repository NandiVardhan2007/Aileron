"""Unit tests for Aileron plugin entry point loading (M7)."""

from unittest.mock import MagicMock, patch

from aileron.plugins import (
    BUILTIN_BACKENDS,
    load_backend_plugins,
    load_gesture_plugins,
)


def test_load_builtin_backend_plugins() -> None:
    """Built-in backends are registered and discoverable."""
    backends = load_backend_plugins()
    for name in ("null", "windows", "linux", "vgamepad", "keyboard_pwm"):
        assert name in backends
        assert backends[name] == BUILTIN_BACKENDS[name]


def test_load_custom_backend_plugin_via_entry_points() -> None:
    """External backend entry points are dynamically discovered."""
    mock_ep = MagicMock()
    mock_ep.name = "custom_wheel"
    mock_ep.value = "my_pkg.wheel:CustomWheelBackend"
    mock_ep.load.return_value = "CustomWheelClass"

    with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
        backends = load_backend_plugins()
        assert "custom_wheel" in backends
        assert backends["custom_wheel"] == "CustomWheelClass"


def test_load_gesture_plugin_via_entry_points() -> None:
    """External gesture entry points are dynamically discovered."""
    mock_ep = MagicMock()
    mock_ep.name = "peace_sign"
    mock_ep.value = "my_pkg.gestures:PeaceDetector"
    mock_ep.load.return_value = "PeaceDetectorClass"

    with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
        gestures = load_gesture_plugins()
        assert "peace_sign" in gestures
        assert gestures["peace_sign"] == "PeaceDetectorClass"
