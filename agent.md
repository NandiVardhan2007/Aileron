# AGENT.md — Aileron

> Read this first, then `rules.md`. If they disagree, `rules.md` wins. Deep details live in `docs/`.

## 1. Mission
Aileron turns a webcam into a touchless input device using the MediaPipe 21-point hand model.
- **Pointer mode:** cursor, click, double/right/middle click, drag, scroll, zoom → OS mouse/keyboard.
- **Cockpit mode:** analog steering, throttle, brake, buttons for car/bike/flight sims → **virtual gamepad**.

Priorities: **safe → predictable → low-latency → configurable → pretty.**
Non-goals: eye tracking, full-body pose, cloud processing, depth-camera-only features.

## 2. Landmark reference (MediaPipe Hands, 21 points)
Always use named constants from `aileron/landmarks.py` (`Lm.INDEX_FINGER_TIP`); never bare numbers.

| Idx | Name | Idx | Name |
|----:|------|----:|------|
| 0 | WRIST | 11 | MIDDLE_FINGER_DIP |
| 1 | THUMB_CMC | 12 | MIDDLE_FINGER_TIP |
| 2 | THUMB_MCP | 13 | RING_FINGER_MCP |
| 3 | THUMB_IP | 14 | RING_FINGER_PIP |
| 4 | THUMB_TIP | 15 | RING_FINGER_DIP |
| 5 | INDEX_FINGER_MCP | 16 | RING_FINGER_TIP |
| 6 | INDEX_FINGER_PIP | 17 | PINKY_MCP |
| 7 | INDEX_FINGER_DIP | 18 | PINKY_PIP |
| 8 | INDEX_FINGER_TIP | 19 | PINKY_DIP |
| 9 | MIDDLE_FINGER_MCP | 20 | PINKY_TIP |
| 10 | MIDDLE_FINGER_PIP | | |

Chains (MCP, PIP, DIP, TIP): index `5-6-7-8`, middle `9-10-11-12`, ring `13-14-15-16`, pinky `17-18-19-20`.
Thumb (CMC, MCP, IP, TIP): `1-2-3-4`.

Key definitions (details in `docs/SIGNAL_PROCESSING.md`):
- **palm_size** = mean(dist(0,9), dist(5,17)). All thresholds are multiples of it (scale-invariant).
- **cursor anchor** = midpoint(5, 9). Knuckles don't move on pinch, so clicks don't nudge the cursor.
- **Frames are mirrored once at capture**, so every downstream coordinate is in the user's view.
  Handedness is resolved once in `vision/hands.py` and verified by the pre-flight check.
- Use `world_landmarks` (metric 3D) for angles/rotation; use image landmarks for screen mapping.

## 3. Architecture in one picture
```
Camera → Capture → HandTracker → Features → Filters → GestureEngine → ModeManager
                                                                         │
HUD ← Telemetry ← SafetyGate ← ActionMapper ← ───────────────────────────┘
                      │
                      ▼
              OutputBackend: Mouse | Keyboard | Gamepad | Null
```
One-way data flow; each stage is replayable from recorded landmarks. Full design: `docs/ARCHITECTURE.md`.

## 4. Modes and gestures (summary — spec lives in `docs/GESTURES.md`)
| Action | Gesture |
|--------|---------|
| Move | Open hand (anchor = knuckles) |
| Left click / drag | Pinch thumb+index: tap / hold |
| Right / middle click | Pinch thumb+middle / thumb+ring |
| Scroll | V-sign, displacement from start point = scroll rate |
| Zoom | Two hands pinching, change spacing → Ctrl+wheel |
| Standby / Arm | Fist hold 0.4 s / open palm hold 0.4 s |
| Mode switch | Shaka hold 0.8 s |
| Kill switch | `Ctrl+Alt+Esc` (OS-level) |

Cockpit profiles (`docs/COCKPIT_MODE.md`): **Yoke** (two-hand wheel angle → steering; index extension →
throttle/brake), **Handlebar** (hand roll → steering), **Stick** (planned, flight sims).

## 5. Repository layout
```
src/aileron/
  landmarks.py  capture/  vision/  features/  filters/  gestures/
  modes/  mapping/  safety/  output/  ui/  config/  replay/  __main__.py
config/defaults.toml   config/profiles/
tests/{unit,replay,safety,fixtures,manual}
tools/{record_session.py, plot_latency.py, tune_filters.py}
docs/
```

| Module | Does | Must not |
|--------|------|----------|
| `capture` | Camera, latest-frame slot | Inference |
| `vision` | HandLandmarker → `HandFrame` | Know gestures |
| `features` | Palm size, curl, pinch ratios, wrist-line angle | Hold state |
| `filters` | One Euro, deadzone, curves | Know the OS |
| `gestures` | Events with hysteresis/debounce | Call OS APIs |
| `modes` | Mode state machine | Emit raw input |
| `mapping` | Events → `Intent` | Touch the OS |
| `safety` | Watchdog, kill switch, neutralize | Be bypassable |
| `output` | Execute intents (mouse/keyboard/gamepad/null) | Contain logic |
| `ui` | HUD, tray, calibration | Block the pipeline |
| `config` | Pydantic models, TOML, profiles | Hide thresholds elsewhere |
| `replay` | Record/replay landmark JSONL | Need a camera |

## 6. Stack
Python 3.11+, uv, MediaPipe **Tasks API** `HandLandmarker` (`LIVE_STREAM`, 2 hands; never legacy `mp.solutions`),
OpenCV, NumPy, Pydantic v2, pynput / native `SendInput`, `vgamepad` (Windows) / `evdev` (Linux), PySide6 (optional),
pytest + hypothesis, ruff, mypy --strict.

## 7. Commands
```bash
uv sync
uv run python -m aileron --backend null --debug      # safe dev mode
uv run python -m aileron --replay tests/replay/pinch_click.jsonl
uv run python tools/record_session.py                # landmarks only, no video
uv run pytest -q && uv run ruff check . && uv run mypy src
```

## 8. How an agent works here
1. Read `rules.md`, then the relevant doc in `docs/`.
2. Use the `null` backend and replays; touch real OS input only when unavoidable and keep the kill switch handy.
3. Smallest change that solves the task; no unrelated refactors.
4. New gesture = spec row + config entry (`on`/`off` thresholds) + unit test + replay fixtures (positive and negative).
5. Thresholds are config, never literals.
6. Latency/smoothing work needs measured before/after numbers.
7. Update docs and `config/defaults.toml` in the same change.

### Definition of done
- [ ] ruff, mypy --strict, pytest (including `-m safety`) pass
- [ ] Unit + replay tests for new behavior
- [ ] No threshold literals in logic
- [ ] Hand-lost / mode-switch / shutdown paths verified: nothing left held
- [ ] Latency budget (`rules.md` §5) still met
- [ ] Docs and defaults updated

## 9. Where to look
Requirements `docs/PRD.md` · Design `docs/ARCHITECTURE.md` · Contracts `docs/INTERFACES.md` ·
Math `docs/SIGNAL_PROCESSING.md` · Gestures `docs/GESTURES.md` · Sims `docs/COCKPIT_MODE.md` ·
Safety `docs/SAFETY.md` · UX `docs/CALIBRATION_UX.md` · Config `docs/CONFIGURATION.md` ·
Tests `docs/TESTING.md` · Plan `docs/ROADMAP.md` · Why `docs/DECISIONS.md`.
