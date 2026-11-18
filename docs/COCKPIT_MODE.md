# Cockpit Mode — Simulator Control

Cockpit mode converts hand pose into analog controller values and sends them through a **virtual gamepad**
so that games see a normal controller.

## 1. Why a virtual gamepad
Keyboard keys are binary; driving needs smooth analog steering and graded throttle/brake. A virtual Xbox-style
gamepad exposes: left stick X/Y, right stick X/Y, left trigger (brake), right trigger (throttle), face
buttons, bumpers (gear shift), D-pad. Most PC racing and flight titles accept it with no per-game integration.

## 2. Profiles

### 2.1 Yoke (two hands, cars and trucks)

Imagine holding a steering wheel; the line between your palms is the wheel.

| Control | Source | Gamepad output |
|---------|--------|----------------|
| Steering | Angle of line L-palm → R-palm (`SIGNAL §8`), ±45° = full lock | Left stick X |
| Throttle | Right index extension (trigger-finger) | Right trigger |
| Brake | Left index extension | Left trigger |
| Gear up / down | Right / left pinch thumb+ring tap | RB / LB |
| Handbrake | Right pinch thumb+pinky | X (configurable) |
| Horn / reset | Left pinch thumb+pinky | Y (configurable) |
| Look / camera | Optional: right palm offset | Right stick |

Rationale: both hands stay in a natural "grip" pose; only the index fingers move for pedals, so steering and
pedals are decoupled. The alternative throttle sources below are evaluated in user studies.

### 2.2 Handlebar (bikes and motorcycles)

| Control | Source | Output |
|---------|--------|--------|
| Steering / lean | Hand roll (`SIGNAL §9`), ±35° | Left stick X |
| Throttle | Thumb curl, or wrist-twist (palm-normal rotation), or index extension (user choice) | Right trigger |
| Brake | Opposite hand index extension | Left trigger |
| Lean forward/back | Optional: hand height | Left stick Y |

Single-hand play is possible with the other hand on the keyboard for gears/buttons.

### 2.3 Stick (flight, planned post-1.0)

| Control | Source | Output |
|---------|--------|--------|
| Roll (aileron) | Hand roll | Right stick X |
| Pitch (elevator) | Hand height or palm pitch | Right stick Y |
| Throttle | Other hand height, or index extension | Right/left trigger or left stick Y |
| Rudder | Other hand roll | Left stick X |

This is where the project name earns its keep: the *aileron* is literally your rolling hand.

## 3. Alternative throttle strategies (to test)

| Strategy | Pros | Cons |
|----------|------|------|
| Index extension (default) | Fast, low arm travel, easy to calibrate | Fingers must stay visible; tiring over long sessions |
| Hand depth (toward camera) | Natural "push" metaphor | Single-camera depth is noisy |
| Thumb curl | Works with a grip pose | Small range, hard to modulate |
| Wrist twist (motorcycle) | Very natural for bikes | Needs reliable palm-normal estimation |
| Hand height of one hand | Large range, easy | Conflicts with steering pose, fatigue |

Decision is data-driven: see `TESTING.md` §7 (user study protocol).

## 4. Response shaping

Each axis: **calibrated neutral → deadzone → normalize by range → expo curve → filter → clamp**.

| Axis | Default deadzone | Default expo | Filter profile |
|------|------------------|--------------|----------------|
| Steering | 3° | 0.35 | smooth, slow `beta` |
| Throttle | 0.05 | 0.0 | fast, higher `beta` |
| Brake | 0.05 | 0.0 | fast |
| Look | 5° | 0.5 | smooth |

Speed-sensitive steering (optional): reduce `steer_max` as game speed increases (needs telemetry; out of scope for v1).

## 5. Safety behaviors (Cockpit-specific)
- Hand lost > 150 ms → steering 0, throttle 0, brake 0 (not "brake 100%": consider game context; configurable `on_loss = "neutral" | "brake"`).
- Start of Cockpit mode requires a **neutral hold**: hands visible and still for 1 s before axes go live.
- Axes ramp in over 200 ms when going live (no sudden steering input).
- Mode toggle gesture is ignored while throttle > 0.3 (avoid accidental exit at speed); kill switch always works.
- Mouse/keyboard events are never emitted in Cockpit mode except for the keyboard fallback (`SAFE-10`).

## 6. Backends

| Platform | Backend | Notes |
|----------|---------|-------|
| Windows | `vgamepad` (virtual Xbox 360 via ViGEmBus) | Requires driver. The ViGEm project has been reported as retired/unmaintained: **verify status before building on it**; keep the backend swappable. Candidates: vJoy, custom signed driver, or keeping the keyboard fallback as the safety net. |
| Linux | `evdev` + `uinput` virtual gamepad | Needs `/dev/uinput` permission (udev rule) |
| macOS | None | Keyboard PWM fallback |
| Any | `KeyboardPwmGamepad` | Emulates analog via pulse-width modulation of arrow/WASD keys at 30–60 Hz; coarse but universal |

## 6.1 Game compatibility notes
- Prefer **offline/single-player** titles. Online games with anti-cheat may reject virtual input drivers (`PRD R7`).
- Many games auto-detect the first connected controller; start Aileron before the game.
- If the game has Steam Input, a virtual pad shows as a standard Xbox controller and can be remapped there.
- Provide a test page (`aileron --gamepad-test`) showing live axes so users verify mapping before launching a game.

## 7. Calibration inputs (from Pre-flight, see `CALIBRATION_UX.md`)
`θ_neutral`, `steer_max` (measured comfortable lock-to-lock), per-hand `ext_min/ext_max` for each trigger finger,
neutral hand roll for Handlebar, and a hand-size reference for `min_palm_size`.
