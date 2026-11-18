"""Unit tests for configuration schema, validation, and defaults loading."""

import pytest
from pydantic import ValidationError

from aileron.config import AileronConfig, ClickConfig, FingersConfig, PrivacyConfig, load_config


def test_load_defaults() -> None:
    """Verify config/defaults.toml loads without validation errors."""
    cfg = load_config()
    assert isinstance(cfg, AileronConfig)
    assert cfg.schema_version == 1
    assert cfg.camera.fps == 60
    assert cfg.tracking.hand_lost_ms == 150
    assert cfg.pointer.mode == "absolute"
    assert cfg.click.pinch_on < cfg.click.pinch_off
    assert cfg.privacy.network is False


def test_invalid_pinch_hysteresis() -> None:
    """Verify that pinch_on >= pinch_off is rejected."""
    with pytest.raises(ValidationError, match="pinch_on"):
        ClickConfig(pinch_on=0.35, pinch_off=0.25)

    with pytest.raises(ValidationError, match="pinch_on"):
        ClickConfig(pinch_on=0.30, pinch_off=0.30)


def test_invalid_extension_hysteresis() -> None:
    """Verify that ext_off >= ext_on is rejected."""
    with pytest.raises(ValidationError, match="ext_off"):
        FingersConfig(ext_on=0.40, ext_off=0.60)


def test_privacy_network_violation() -> None:
    """Verify PRIV-01 rule: network must never be set to True."""
    with pytest.raises(ValidationError, match="PRIV-01 violated"):
        PrivacyConfig(network=True)
