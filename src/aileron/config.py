"""Configuration schema and loader for Aileron."""

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CameraConfig(BaseModel):
    """Camera capture configuration."""

    model_config = ConfigDict(extra="forbid")

    device: int = Field(0, description="Camera index or device identifier")
    width: int = Field(1280, ge=320, le=3840, description="Requested capture width in pixels")
    height: int = Field(720, ge=240, le=2160, description="Requested capture height in pixels")
    fps: int = Field(60, ge=15, le=240, description="Requested capture framerate in frames/second")
    mirror: bool = Field(True, description="Mirror frames horizontally once at capture")
    buffer_size: int = Field(
        1, ge=1, le=5, description="Capture buffer queue size (1 = latest frame only)"
    )


class TrackingConfig(BaseModel):
    """Hand tracking and landmark inference configuration."""

    model_config = ConfigDict(extra="forbid")

    num_hands: int = Field(2, ge=1, le=2, description="Maximum hands to detect simultaneously")
    min_detection_conf: float = Field(
        0.6, ge=0.1, le=1.0, description="Detector confidence threshold"
    )
    min_presence_conf: float = Field(
        0.6, ge=0.1, le=1.0, description="Presence confidence threshold"
    )
    min_tracking_conf: float = Field(
        0.6, ge=0.1, le=1.0, description="Landmark tracking confidence threshold"
    )
    min_hand_conf: float = Field(
        0.6, ge=0.1, le=1.0, description="Overall hand confidence threshold"
    )
    min_palm_size: float = Field(
        0.05, ge=0.01, le=0.5, description="Minimum palm size in normalized image coordinates"
    )
    hand_lost_ms: int = Field(
        150, ge=50, le=1000, description="Milliseconds without hand before neutralizing inputs"
    )
    engage_ms: int = Field(
        300, ge=50, le=2000, description="Milliseconds hand must be stable before engaging cursor"
    )
    dwell_grace_ms: int = Field(
        100,
        ge=0,
        le=500,
        description="Grace period in ms where dwell pauses rather than resets on dropout",
    )
    primary_hand: Literal["either", "left", "right"] = Field(
        "either", description="Preferred primary hand"
    )


class LoopConfig(BaseModel):
    """Control loop timing configuration."""

    model_config = ConfigDict(extra="forbid")

    tick_hz: int = Field(120, ge=30, le=240, description="Fixed control loop rate in Hz")
    heartbeat_stale_ms: int = Field(
        250, ge=50, le=1000, description="Watchdog timeout before triggering fault"
    )


class OneEuroConfig(BaseModel):
    """Parameters for 1D One Euro filter."""

    model_config = ConfigDict(extra="forbid")

    min_cutoff: float = Field(1.0, gt=0.01, le=50.0, description="Minimum cutoff frequency in Hz")
    beta: float = Field(1.0, ge=0.0, le=100.0, description="Speed coefficient")
    d_cutoff: float = Field(1.0, gt=0.01, le=50.0, description="Derivative cutoff frequency in Hz")


class FiltersConfig(BaseModel):
    """Filter parameters per continuous signal channel."""

    model_config = ConfigDict(extra="forbid")

    cursor: OneEuroConfig = Field(
        default_factory=lambda: OneEuroConfig(min_cutoff=1.2, beta=8.0, d_cutoff=1.0)
    )
    scroll: OneEuroConfig = Field(
        default_factory=lambda: OneEuroConfig(min_cutoff=1.0, beta=4.0, d_cutoff=1.0)
    )
    steering: OneEuroConfig = Field(
        default_factory=lambda: OneEuroConfig(min_cutoff=0.9, beta=3.0, d_cutoff=1.0)
    )
    trigger: OneEuroConfig = Field(
        default_factory=lambda: OneEuroConfig(min_cutoff=2.5, beta=15.0, d_cutoff=1.0)
    )


class PointerConfig(BaseModel):
    """Pointer mode cursor positioning and active region configuration."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["absolute", "relative"] = Field("absolute", description="Cursor mapping mode")
    region_w: float = Field(
        0.60, ge=0.1, le=1.0, description="Normalized width of camera active interaction region"
    )
    region_h: float = Field(
        0.50, ge=0.1, le=1.0, description="Normalized height of camera active interaction region"
    )
    region_cx: float = Field(
        0.50, ge=0.1, le=0.9, description="Normalized center X of interaction region"
    )
    region_cy: float = Field(
        0.55, ge=0.1, le=0.9, description="Normalized center Y of interaction region"
    )
    gamma: float = Field(
        1.0, ge=0.2, le=3.0, description="Center/edge non-linear sensitivity exponent"
    )
    relative_gain: float = Field(
        1800.0, ge=100.0, le=10000.0, description="Pixel move scale factor for relative mode"
    )
    accel: float = Field(
        0.5,
        ge=0.0,
        le=5.0,
        description="Speed-dependent acceleration coefficient for relative mode",
    )
    min_move_px: int = Field(
        1, ge=0, le=50, description="Minimum pixel displacement to emit a move intent"
    )
    freeze_damping: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        description="Damping factor while pinch is pending (1.0 = fully frozen)",
    )
    anchor: list[str] = Field(
        default_factory=lambda: ["INDEX_FINGER_MCP", "MIDDLE_FINGER_MCP"],
        description="Landmarks defining cursor anchor midpoint",
    )


class ClickConfig(BaseModel):
    """Pinch click and drag gesture parameters."""

    model_config = ConfigDict(extra="forbid")

    pinch_on: float = Field(
        0.25, ge=0.05, le=0.5, description="Pinch ratio threshold to activate pinch"
    )
    pinch_off: float = Field(
        0.35, ge=0.1, le=0.8, description="Pinch ratio threshold to release pinch"
    )
    min_pinch_ms: int = Field(
        40, ge=10, le=200, description="Minimum pinch duration to avoid noise spikes"
    )
    tap_ms: int = Field(
        300, ge=50, le=1000, description="Maximum pinch hold duration for a tap click vs drag"
    )
    dbl_ms: int = Field(
        350, ge=100, le=1000, description="Maximum interval between clicks for double-click"
    )
    margin: float = Field(
        0.08, ge=0.01, le=0.3, description="Minimum separation margin between adjacent pinch ratios"
    )
    max_clicks_per_s: int = Field(
        8, ge=1, le=30, description="Rate limit cap on clicks emitted per second"
    )

    @model_validator(mode="after")
    def validate_pinch_hysteresis(self) -> "ClickConfig":
        if self.pinch_on >= self.pinch_off:
            raise ValueError(
                f"pinch_on ({self.pinch_on}) must be less than pinch_off ({self.pinch_off})"
            )
        return self


class ScrollConfig(BaseModel):
    """V-sign scroll parameters."""

    model_config = ConfigDict(extra="forbid")

    deadzone: float = Field(
        0.15, ge=0.0, le=0.5, description="Displacement deadzone in palm_size units"
    )
    gain: float = Field(
        40.0, ge=1.0, le=200.0, description="Gain factor mapping displacement to lines/s"
    )
    power: float = Field(
        1.5, ge=1.0, le=3.0, description="Power curve exponent for progressive scroll rate"
    )
    max_lines_per_s: float = Field(
        60.0, ge=5.0, le=300.0, description="Maximum lines scrolled per second"
    )
    hold_ms: int = Field(
        120, ge=30, le=500, description="Required V-sign pose hold time before scrolling begins"
    )


class ZoomConfig(BaseModel):
    """Two-hand zoom parameters."""

    model_config = ConfigDict(extra="forbid")

    step_fraction: float = Field(
        0.06, ge=0.01, le=0.3, description="Fractional hand spacing change per zoom step"
    )
    require_both_pinch_ms: int = Field(
        80, ge=20, le=300, description="Dwell time both hands must pinch before zoom starts"
    )
    method: Literal["ctrl_wheel", "ctrl_plusminus"] = Field(
        "ctrl_wheel", description="Zoom emission method"
    )


class FingersConfig(BaseModel):
    """Finger extension thresholds and joint angle reference values."""

    model_config = ConfigDict(extra="forbid")

    theta_curled_deg: float = Field(
        70.0, ge=30.0, le=120.0, description="Joint angle considered fully curled"
    )
    theta_straight_deg: float = Field(
        170.0, ge=120.0, le=180.0, description="Joint angle considered fully extended"
    )
    ext_on: float = Field(
        0.75,
        ge=0.4,
        le=1.0,
        description="Normalized extension threshold to consider finger extended",
    )
    ext_off: float = Field(
        0.35, ge=0.0, le=0.6, description="Normalized extension threshold to consider finger curled"
    )

    @model_validator(mode="after")
    def validate_extension_hysteresis(self) -> "FingersConfig":
        if self.ext_off >= self.ext_on:
            raise ValueError(f"ext_off ({self.ext_off}) must be less than ext_on ({self.ext_on})")
        return self


class SessionConfig(BaseModel):
    """Session state and dwell durations."""

    model_config = ConfigDict(extra="forbid")

    start_armed: bool = Field(
        False, description="Start system directly in armed state (not recommended)"
    )
    clutch_ms: int = Field(
        400, ge=100, le=2000, description="Fist hold duration to enter standby (clutch)"
    )
    resume_ms: int = Field(
        400, ge=100, le=2000, description="Open palm hold duration to resume from standby"
    )
    arm_ms: int = Field(
        800, ge=200, le=3000, description="Open palm hold duration to arm from disarmed"
    )
    mode_ms: int = Field(800, ge=200, le=3000, description="Shaka hold duration to toggle modes")
    kill_switch_hotkey: str = Field("ctrl+alt+esc", description="Global kill switch hotkey chord")
    fatigue_reminder_min: int = Field(
        15, ge=1, le=120, description="Minutes of continuous activity before rest hint"
    )


class CockpitYokeConfig(BaseModel):
    """Yoke profile parameters for Cockpit mode."""

    model_config = ConfigDict(extra="forbid")

    steer_max_deg: float = Field(
        45.0, ge=15.0, le=90.0, description="Steering wheel lock-to-lock angle in degrees"
    )
    steer_deadzone_deg: float = Field(
        3.0, ge=0.0, le=15.0, description="Center steering deadzone in degrees"
    )
    steer_expo: float = Field(
        0.35, ge=0.0, le=1.0, description="Steering non-linear exponential curve factor"
    )
    throttle_source: str = Field("right_index", description="Feature used for throttle axis")
    brake_source: str = Field("left_index", description="Feature used for brake axis")
    trigger_deadzone: float = Field(
        0.05, ge=0.0, le=0.3, description="Trigger finger rest deadzone"
    )
    trigger_curve: float = Field(1.0, ge=0.5, le=3.0, description="Trigger curve exponent")


class CockpitHandlebarConfig(BaseModel):
    """Handlebar profile parameters for Cockpit mode."""

    model_config = ConfigDict(extra="forbid")

    steer_max_deg: float = Field(
        35.0, ge=10.0, le=75.0, description="Handlebar lean angle in degrees"
    )
    steer_deadzone_deg: float = Field(
        3.0, ge=0.0, le=15.0, description="Center lean deadzone in degrees"
    )
    steer_expo: float = Field(0.35, ge=0.0, le=1.0, description="Handlebar non-linear curve factor")
    throttle_source: Literal["thumb_curl", "wrist_twist", "index"] = Field(
        "thumb_curl", description="Throttle source"
    )
    brake_source: str = Field("off_hand_index", description="Brake source")


class CockpitButtonsConfig(BaseModel):
    """Button gesture bindings for Cockpit mode."""

    model_config = ConfigDict(extra="forbid")

    gear_up: str = Field("right_pinch_ring", description="Gear up trigger binding")
    gear_down: str = Field("left_pinch_ring", description="Gear down trigger binding")
    handbrake: str = Field("right_pinch_pinky", description="Handbrake trigger binding")
    horn: str = Field("left_pinch_pinky", description="Horn / reset trigger binding")


class CockpitConfig(BaseModel):
    """Cockpit simulator mode configuration."""

    model_config = ConfigDict(extra="forbid")

    profile: Literal["yoke", "handlebar", "stick"] = Field(
        "yoke", description="Active simulator profile"
    )
    on_loss: Literal["neutral", "brake"] = Field("neutral", description="Action when hand is lost")
    neutral_hold_ms: int = Field(
        1000, ge=100, le=5000, description="Required neutral hold time before axes go live"
    )
    ramp_in_ms: int = Field(
        200, ge=0, le=1000, description="Axis ramp-in time to prevent sudden steering jumps"
    )
    mode_toggle_block_throttle: float = Field(
        0.3, ge=0.0, le=1.0, description="Throttle threshold above which mode toggle is blocked"
    )
    backend: Literal["auto", "vgamepad", "uinput", "keyboard_pwm"] = Field(
        "auto", description="Gamepad backend"
    )
    yoke: CockpitYokeConfig = Field(default_factory=CockpitYokeConfig)
    handlebar: CockpitHandlebarConfig = Field(default_factory=CockpitHandlebarConfig)
    buttons: CockpitButtonsConfig = Field(default_factory=CockpitButtonsConfig)


class UIConfig(BaseModel):
    """HUD visual overlay configuration."""

    model_config = ConfigDict(extra="forbid")

    hud: bool = Field(True, description="Enable on-screen HUD")
    hud_mode: Literal["compact", "full"] = Field("compact", description="HUD layout style")
    debug_panel: bool = Field(False, description="Show live latency and FPS debug metrics")
    reduced_motion: bool = Field(
        False, description="Disable animated dwell rings and flashing indicators"
    )
    audio_cues: bool = Field(False, description="Play audio cues on state and gesture events")


class AccessibilityConfig(BaseModel):
    """Accessibility enhancements."""

    model_config = ConfigDict(extra="forbid")

    stability_mode: bool = Field(
        False,
        description="Enable heavier smoothing and wider gesture thresholds for tremor support",
    )
    dwell_click: bool = Field(False, description="Hover to click for users unable to pinch")
    dwell_click_ms: int = Field(
        900, ge=200, le=3000, description="Dwell hover duration for dwell click"
    )


class LoggingConfig(BaseModel):
    """Logging settings."""

    model_config = ConfigDict(extra="forbid")

    level: str = Field("INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    file: bool = Field(True, description="Write logs to local file")
    max_mb: int = Field(10, ge=1, le=100, description="Maximum log file size before rotation")


class BlackboxConfig(BaseModel):
    """Landmark ring buffer for debugging and crash reports."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(False, description="Opt-in black box recorder")
    seconds: int = Field(
        10, ge=1, le=60, description="Seconds of landmark history to keep in memory"
    )
    dump_on_fault: bool = Field(True, description="Dump landmark history to disk on safety fault")


class PrivacyConfig(BaseModel):
    """Privacy invariants."""

    model_config = ConfigDict(extra="forbid")

    network: bool = Field(False, description="Network access prohibition (must remain false)")

    @field_validator("network")
    @classmethod
    def validate_network(cls, v: bool) -> bool:
        if v:
            raise ValueError("PRIV-01 violated: network must remain false in Aileron")
        return v


class CalibrationData(BaseModel):
    """User-specific physical calibration offsets."""

    model_config = ConfigDict(extra="allow")

    theta_neutral_deg: float = Field(0.0, description="Neutral wheel angle offset")
    steer_max_deg: float | None = Field(None, description="Custom measured lock-to-lock angle")
    right_index_ext_min: float | None = Field(None, description="Right index curled extension")
    right_index_ext_max: float | None = Field(None, description="Right index straight extension")
    left_index_ext_min: float | None = Field(None, description="Left index curled extension")
    left_index_ext_max: float | None = Field(None, description="Left index straight extension")


class AileronConfig(BaseModel):
    """Root configuration model for Aileron."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(1, description="Configuration schema version for migrations")
    camera: CameraConfig = Field(default_factory=CameraConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)
    pointer: PointerConfig = Field(default_factory=PointerConfig)
    click: ClickConfig = Field(default_factory=ClickConfig)
    scroll: ScrollConfig = Field(default_factory=ScrollConfig)
    zoom: ZoomConfig = Field(default_factory=ZoomConfig)
    fingers: FingersConfig = Field(default_factory=FingersConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    cockpit: CockpitConfig = Field(default_factory=CockpitConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    accessibility: AccessibilityConfig = Field(default_factory=AccessibilityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    blackbox: BlackboxConfig = Field(default_factory=BlackboxConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    calibration: CalibrationData | None = Field(default=None, description="Calibrated offsets")


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively update nested dictionaries."""
    res = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and k in res and isinstance(res[k], dict):
            res[k] = _deep_update(res[k], v)
        else:
            res[k] = v
    return res


def load_config(
    defaults_path: Path | str | None = None,
    profile_path: Path | str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AileronConfig:
    """Load configuration with standard precedence: defaults -> profile -> CLI overrides."""
    if defaults_path is None:
        defaults_path = Path(__file__).resolve().parent.parent.parent / "config" / "defaults.toml"
    else:
        defaults_path = Path(defaults_path)

    if not defaults_path.is_file():
        raise FileNotFoundError(f"Configuration defaults file not found: {defaults_path}")

    with open(defaults_path, "rb") as f:
        data = tomllib.load(f)

    if profile_path is not None:
        p_path = Path(profile_path)
        if p_path.is_file():
            with open(p_path, "rb") as pf:
                profile_data = tomllib.load(pf)
                data = _deep_update(data, profile_data)
        else:
            raise FileNotFoundError(f"Profile file not found: {profile_path}")

    if cli_overrides:
        data = _deep_update(data, cli_overrides)

    return AileronConfig.model_validate(data)
