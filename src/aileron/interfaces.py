"""Data contracts and immutable message interfaces for Aileron."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol

import numpy as np


class Side(Enum):
    """Handedness from the user's point of view."""

    LEFT = "left"
    RIGHT = "right"


class SessionState(Enum):
    """Session-level operational state."""

    BOOT = "boot"
    DISARMED = "disarmed"
    ARMED = "armed"
    STANDBY = "standby"
    FAULT = "fault"


class ActiveMode(Enum):
    """Primary interaction mode."""

    POINTER = "pointer"
    COCKPIT = "cockpit"


class CockpitProfileKind(Enum):
    """Active cockpit control profile."""

    YOKE = "yoke"
    HANDLEBAR = "handlebar"
    STICK = "stick"


@dataclass(frozen=True, slots=True)
class Frame:
    """Raw camera frame captured from sensor."""

    t_capture_ns: int
    seq: int
    image: np.ndarray  # BGR uint8, already mirrored; never persisted


@dataclass(frozen=True, slots=True)
class Hand:
    """Estimated hand tracking landmarks."""

    side: Side
    score: float  # tracking confidence 0..1
    lm: np.ndarray  # (21, 3) image-normalized x, y in [0, 1], z relative
    world: np.ndarray  # (21, 3) metric, hand-centered in meters


@dataclass(frozen=True, slots=True)
class HandFrame:
    """Tracker result with 0..2 detected hands."""

    t_capture_ns: int
    t_infer_done_ns: int
    seq: int
    hands: tuple[Hand, ...]


@dataclass(frozen=True, slots=True)
class HandFeatures:
    """Extracted geometric features for one hand."""

    side: Side
    valid: bool  # False if NaN or degenerate
    palm_size: float  # scale unit in normalized image coordinates
    anchor: tuple[float, float]  # cursor anchor midpoint(INDEX_MCP, MIDDLE_MCP)
    curl: dict[str, float]  # finger -> extension 0..1 (0 curled, 1 straight)
    pinch: dict[str, float]  # "index"|"middle"|"ring"|"pinky" -> distance / palm_size
    roll_deg: float  # wrist -> middle_mcp angle vs vertical (world)
    palm_normal: np.ndarray  # (3,) unit vector
    palm_center: tuple[float, float]  # center of palm in image coordinates
    v_gap: float = 0.0  # normalized index-middle fingertip separation


class GestureKind(Enum):
    """Discrete gesture event types."""

    CLICK_LEFT = "click_left"
    DOUBLE_CLICK = "double_click"
    CLICK_RIGHT = "click_right"
    CLICK_MIDDLE = "click_middle"
    DRAG_START = "drag_start"
    DRAG_END = "drag_end"
    SCROLL_START = "scroll_start"
    SCROLL_END = "scroll_end"
    ZOOM_START = "zoom_start"
    ZOOM_END = "zoom_end"
    CLUTCH = "clutch"
    RESUME = "resume"
    MODE_TOGGLE = "mode_toggle"
    ENGAGED = "engaged"
    DISENGAGED = "disengaged"


@dataclass(frozen=True, slots=True)
class GestureEvent:
    """Discrete gesture event."""

    kind: GestureKind
    t_ns: int
    side: Side | None


@dataclass(frozen=True, slots=True)
class Signals:
    """Continuous control signals for a control tick."""

    cursor: tuple[float, float] | None = None  # filtered normalized anchor (u, v)
    scroll_rate: tuple[float, float] = (0.0, 0.0)  # lines/s (x, y)
    zoom_delta: float = 0.0  # relative spacing change this tick
    wheel_angle_deg: float | None = None  # Yoke steering angle
    hand_roll_deg: float | None = None  # Handlebar roll
    index_extension: dict[Side, float] | None = None  # 0..1 per hand
    dwell_progress: dict[str, float] | None = None  # name -> 0..1 for HUD rings


@dataclass(frozen=True, slots=True)
class GestureOutput:
    """Combined output of gesture recognition pipeline for a tick."""

    t_ns: int
    events: tuple[GestureEvent, ...]
    signals: Signals


class Button(Enum):
    """Mouse buttons."""

    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class PadButton(Enum):
    """Gamepad buttons."""

    A = "A"
    B = "B"
    X = "X"
    Y = "Y"
    LB = "LB"
    RB = "RB"
    START = "START"
    BACK = "BACK"
    DPAD_UP = "DPAD_UP"
    DPAD_DOWN = "DPAD_DOWN"
    DPAD_LEFT = "DPAD_LEFT"
    DPAD_RIGHT = "DPAD_RIGHT"


# Intent hierarchy
@dataclass(frozen=True, slots=True)
class MoveTo:
    """Absolute cursor move in virtual desktop pixels."""

    x: int
    y: int


@dataclass(frozen=True, slots=True)
class MoveBy:
    """Relative cursor move in pixels."""

    dx: int
    dy: int


@dataclass(frozen=True, slots=True)
class ButtonDown:
    """Mouse button down."""

    button: Button


@dataclass(frozen=True, slots=True)
class ButtonUp:
    """Mouse button up."""

    button: Button


@dataclass(frozen=True, slots=True)
class Click:
    """Discrete mouse click."""

    button: Button
    count: int = 1


@dataclass(frozen=True, slots=True)
class Scroll:
    """Wheel scroll in lines."""

    dx: float
    dy: float


@dataclass(frozen=True, slots=True)
class Zoom:
    """Zoom step (+1 zoom in, -1 zoom out)."""

    steps: int


@dataclass(frozen=True, slots=True)
class Key:
    """Keyboard key down or up."""

    chord: str
    down: bool


@dataclass(frozen=True, slots=True)
class Axis:
    """Analog gamepad stick axis."""

    name: Literal["lx", "ly", "rx", "ry"]
    value: float  # clamped -1.0 .. 1.0


@dataclass(frozen=True, slots=True)
class Trigger:
    """Analog gamepad trigger."""

    name: Literal["lt", "rt"]
    value: float  # clamped 0.0 .. 1.0


@dataclass(frozen=True, slots=True)
class Pad:
    """Gamepad button press/release."""

    button: PadButton
    down: bool


@dataclass(frozen=True, slots=True)
class ReleaseAll:
    """Safety neutralizer: immediately release all held inputs."""


Intent = (
    MoveTo
    | MoveBy
    | ButtonDown
    | ButtonUp
    | Click
    | Scroll
    | Zoom
    | Key
    | Axis
    | Trigger
    | Pad
    | ReleaseAll
)


class Filter1D(Protocol):
    """Protocol for a 1D filter (e.g. One Euro)."""

    def __call__(self, x: float, t_ns: int) -> float: ...
    def reset(self) -> None: ...


class GestureDetector(Protocol):
    """Protocol for discrete gesture state machines."""

    name: str

    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]: ...
    def reset(self) -> None: ...


class OutputBackend(Protocol):
    """Protocol for an output backend (mouse, keyboard, gamepad, null)."""

    name: str
    capabilities: frozenset[str]

    def open(self) -> None: ...
    def close(self) -> None: ...
    def apply(self, intents: Sequence[Intent]) -> None: ...
    def release_all(self) -> None: ...
    def held(self) -> frozenset[str]: ...
