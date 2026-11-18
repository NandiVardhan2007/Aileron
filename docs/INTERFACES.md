# Interfaces and Data Contracts — Aileron

Reference signatures (Python 3.11). These are **contracts**: implementations may differ internally, but not at
the boundaries. All message types are `@dataclass(frozen=True, slots=True)`. All timestamps are
`time.monotonic_ns()` integers.

## 1. Constants

```python
# landmarks.py
from enum import IntEnum

class Lm(IntEnum):
    WRIST = 0
    THUMB_CMC = 1; THUMB_MCP = 2; THUMB_IP = 3; THUMB_TIP = 4
    INDEX_FINGER_MCP = 5; INDEX_FINGER_PIP = 6; INDEX_FINGER_DIP = 7; INDEX_FINGER_TIP = 8
    MIDDLE_FINGER_MCP = 9; MIDDLE_FINGER_PIP = 10; MIDDLE_FINGER_DIP = 11; MIDDLE_FINGER_TIP = 12
    RING_FINGER_MCP = 13; RING_FINGER_PIP = 14; RING_FINGER_DIP = 15; RING_FINGER_TIP = 16
    PINKY_MCP = 17; PINKY_PIP = 18; PINKY_DIP = 19; PINKY_TIP = 20

FINGER_CHAINS = {
    "thumb":  (Lm.THUMB_CMC, Lm.THUMB_MCP, Lm.THUMB_IP, Lm.THUMB_TIP),
    "index":  (Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP),
    "middle": (Lm.MIDDLE_FINGER_MCP, Lm.MIDDLE_FINGER_PIP, Lm.MIDDLE_FINGER_DIP, Lm.MIDDLE_FINGER_TIP),
    "ring":   (Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP),
    "pinky":  (Lm.PINKY_MCP, Lm.PINKY_PIP, Lm.PINKY_DIP, Lm.PINKY_TIP),
}
```

## 2. Sensing and perception types

```python
class Side(Enum): LEFT = "left"; RIGHT = "right"      # user's point of view

@dataclass(frozen=True, slots=True)
class Frame:
    t_capture_ns: int
    seq: int
    image: np.ndarray            # BGR uint8, already mirrored; never persisted

@dataclass(frozen=True, slots=True)
class Hand:
    side: Side
    score: float                 # handedness/tracking confidence 0..1
    lm: np.ndarray               # (21, 3) image-normalized x,y in 0..1, z relative
    world: np.ndarray            # (21, 3) metric, hand-centered (meters)

@dataclass(frozen=True, slots=True)
class HandFrame:
    t_capture_ns: int
    t_infer_done_ns: int
    seq: int
    hands: tuple[Hand, ...]      # 0..2

@dataclass(frozen=True, slots=True)
class HandFeatures:
    side: Side
    valid: bool                  # False if NaN/degenerate
    palm_size: float             # normalized image units
    anchor: tuple[float, float]  # midpoint(INDEX_MCP, MIDDLE_MCP)
    curl: dict[str, float]       # finger -> extension 0..1 (0 curled, 1 straight)
    pinch: dict[str, float]      # "index"|"middle"|"ring"|"pinky" -> dist(thumb_tip, tip)/palm_size
    roll_deg: float              # wrist->middle_mcp angle vs vertical (world)
    palm_normal: np.ndarray      # (3,) unit vector
    palm_center: tuple[float, float]
```

## 3. Gesture layer

```python
class GestureKind(Enum):
    CLICK_LEFT; DOUBLE_CLICK; CLICK_RIGHT; CLICK_MIDDLE
    DRAG_START; DRAG_END
    SCROLL_START; SCROLL_END
    ZOOM_START; ZOOM_END
    CLUTCH; RESUME; MODE_TOGGLE
    ENGAGED; DISENGAGED

@dataclass(frozen=True, slots=True)
class GestureEvent:
    kind: GestureKind
    t_ns: int
    side: Side | None

@dataclass(frozen=True, slots=True)
class Signals:                      # continuous values for this tick
    cursor: tuple[float, float] | None        # filtered normalized anchor
    scroll_rate: tuple[float, float]          # lines/s (x, y)
    zoom_delta: float                         # relative spacing change this tick
    wheel_angle_deg: float | None             # Yoke
    hand_roll_deg: float | None               # Handlebar / Stick
    index_extension: dict[Side, float]        # 0..1
    dwell_progress: dict[str, float]          # name -> 0..1 for HUD rings

@dataclass(frozen=True, slots=True)
class GestureOutput:
    t_ns: int
    events: tuple[GestureEvent, ...]
    signals: Signals

class GestureDetector(Protocol):
    name: str
    def update(self, feats: Sequence[HandFeatures], t_ns: int) -> Sequence[GestureEvent]: ...
    def reset(self) -> None: ...        # called on hand loss / mode change
```

## 4. Intents (what the system wants the OS to do)

```python
class Button(Enum): LEFT; RIGHT; MIDDLE
class PadButton(Enum): A; B; X; Y; LB; RB; START; BACK; DPAD_UP; DPAD_DOWN; DPAD_LEFT; DPAD_RIGHT

Intent = (
    MoveTo(x: int, y: int)                 # virtual-desktop pixels
  | MoveBy(dx: int, dy: int)
  | ButtonDown(Button) | ButtonUp(Button) | Click(Button, count: int = 1)
  | Scroll(dx: float, dy: float)           # wheel "lines"
  | Zoom(steps: int)                       # emitted as Ctrl+wheel
  | Key(chord: str, down: bool)
  | Axis(name: Literal["lx","ly","rx","ry"], value: float)       # -1..1
  | Trigger(name: Literal["lt","rt"], value: float)              # 0..1
  | Pad(PadButton, down: bool)
  | ReleaseAll()
)
```

## 5. Output backend protocol

```python
class OutputBackend(Protocol):
    name: str
    capabilities: frozenset[str]           # {"mouse","keyboard","gamepad"}
    def open(self) -> None: ...
    def close(self) -> None: ...           # must call release_all()
    def apply(self, intents: Sequence[Intent]) -> None: ...
    def release_all(self) -> None: ...     # idempotent, never raises, <1 ms
    def held(self) -> frozenset[str]: ...  # for the safety ledger and tests
```

Implementations: `WindowsMouseKeyboard`, `UInputMouseKeyboard`, `QuartzMouseKeyboard`, `VGamepad`, `UInputGamepad`,
`KeyboardPwmGamepad`, `NullBackend` (records intents), `RecordingBackend` (wraps another).

## 6. Filter protocol

```python
class Filter1D(Protocol):
    def __call__(self, x: float, t_ns: int) -> float: ...
    def reset(self) -> None: ...
```
`OneEuroFilter(min_cutoff, beta, d_cutoff)` is the default; see `SIGNAL_PROCESSING.md`.

## 7. Safety gate

```python
class SafetyGate:
    def filter(self, intents: Sequence[Intent], now_ns: int) -> list[Intent]:
        """Drops intents when disarmed/faulted, clamps values, rate-limits,
        maintains the held-input ledger, and prepends ReleaseAll on state change."""
    def on_state_change(self, old: SessionState, new: SessionState) -> list[Intent]: ...
    def heartbeat(self, now_ns: int) -> None: ...       # called each control tick
```

## 8. Replay file format (JSONL)

One JSON object per line. First line is a header.

```json
{"type":"header","schema":1,"app":"aileron","fps_nominal":60,"mirrored":true,"notes":"pinch click, slow"}
{"type":"frame","t_ns":0,"seq":0,"hands":[{"side":"right","score":0.97,"lm":[[0.51,0.62,0.0],"... 21 ..."],"world":[[0.0,0.0,0.0],"... 21 ..."]}]}
{"type":"expect","t_ns":412000000,"event":"CLICK_LEFT"}
```
`expect` lines are optional and used by replay tests as golden outputs. **No pixels are ever stored.**
