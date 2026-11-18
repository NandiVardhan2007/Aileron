# ✈ Aileron

> **Fly your cursor. Steer your sim. No hardware — just your hands.**

An *aileron* is the hinged surface on an aircraft wing that rolls the plane. Tilt your hand and Aileron
does the same for your computer: it turns a plain webcam into a touchless input device that works as a
**mouse** (move, click, drag, scroll, zoom) and as a **flight-deck controller** for racing, bike and
flight simulators (analog steering, throttle, brake) through a virtual gamepad.

Built on the MediaPipe 21-point hand model. Everything runs locally; no video ever leaves your machine.

---

## Modes at a glance

| Mode | What it does | Output |
|------|--------------|--------|
| **Pointer** | Cursor, click, double/right/middle click, drag, scroll, zoom | OS mouse and keyboard events |
| **Cockpit** | Steering, throttle, brake, gear and buttons for simulators | Virtual Xbox 360 gamepad |
| **Standby** | Tracking visible, all output paused | None |

Cockpit profiles: **Yoke** (two-hand wheel for cars), **Handlebar** (bikes), **Stick** (flight sims, planned).

## Gesture cheat sheet (defaults)

| Gesture | Action |
|---------|--------|
| Open hand, move | Move cursor |
| Pinch thumb + index (tap) | Left click |
| Pinch thumb + index (hold) | Drag |
| Pinch thumb + middle | Right click |
| V-sign, move hand up/down | Scroll |
| Two hands pinching, spread / close | Zoom |
| Closed fist (hold 0.4 s) | Standby (clutch) |
| Open palm (hold 0.4 s) | Arm / resume |
| Shaka 🤙 (hold 0.8 s) | Switch Pointer ↔ Cockpit |
| `Ctrl+Alt+Esc` | **Kill switch** (always works) |

## Requirements

- Python 3.11+, a webcam (720p / 30 fps minimum, 60 fps recommended), decent front lighting
- Windows 10/11 (primary), Linux (X11/uinput), macOS (Pointer mode; Cockpit via keyboard fallback)
- Cockpit mode on Windows needs a virtual-gamepad driver (see `docs/COCKPIT_MODE.md`)

## Quick start

```bash
# 1. Install dependencies
uv sync

# 2. Safe dry-run (Overlay & telemetry only, no OS input injection)
uv run aileron --backend null --debug

# 3. Interactive calibration wizard (Lock-to-lock, neutral wheel angle, trigger bounds)
uv run python -m aileron.calibration.wizard --profile default

# 4. Interactive gamepad axis and trigger ASCII viewer
uv run aileron --gamepad-test

# 5. Live control (Starts DISARMED; hold open palm 0.4s to arm; Ctrl+Alt+Esc to panic stop)
uv run aileron
```

## CLI flags reference

- `--backend {auto,null,mouse,gamepad}`: Select output backend (default: `auto`).
- `--profile NAME`: Layer user profile from `config/profiles/<NAME>.toml`.
- `--debug`: Enable live HUD telemetry chips and OpenCV overlay.
- `--no-hud`: Run headless without preview overlay window.
- `--replay FILE`: Replay synthetic or recorded JSONL landmark session.
- `--record FILE`: Record tracked hand landmarks to JSONL format (`PRIV-02`).
- `--gamepad-test`: Run live terminal-based axis and trigger visualizer.
- `--panic`: Broadcast an emergency neutral-release signal to running instances.
- `--print-config`: Print active resolved configuration in TOML format.

## Safety first

Aileron starts **disarmed**, releases everything if it loses your hand for 150 ms, and has a global kill
switch. Read `docs/SAFETY.md` before using Cockpit mode with a real game.

## Documentation map

| Document | Purpose |
|----------|---------|
| `docs/PRD.md` | Vision, users, requirements, metrics, risks |
| `docs/ARCHITECTURE.md` | System design, diagrams, threading, state machines |
| `docs/INTERFACES.md` | Data models and protocols (the contracts between modules) |
| `docs/SIGNAL_PROCESSING.md` | Filters, mapping math, feature extraction |
| `docs/GESTURES.md` | Gesture specification and detection algorithms |
| `docs/COCKPIT_MODE.md` | Simulator profiles, axis mapping, gamepad backends |
| `docs/SAFETY.md` | Hazard analysis, privacy, fail-safe design |
| `docs/CALIBRATION_UX.md` | Pre-flight calibration, HUD, accessibility |
| `docs/CONFIGURATION.md` | Every setting explained (`config/defaults.toml`) |
| `docs/TESTING.md` | Test strategy, replay format, benchmarks, user studies |
| `docs/ROADMAP.md` | Milestones with exit criteria |
| `docs/DECISIONS.md` | Architecture decision records |
| `docs/BRANDING.md` | Name, vocabulary, visual identity |
| `agent.md`, `rules.md` | Guides for AI/human contributors (read these first) |

## Status

**Release Candidate v0.1.0-rc1** (Milestones M0–M7 implemented, verified via unit, replay, and safety suites). See `docs/ROADMAP.md`.

## License

To be decided (MIT or Apache-2.0 suggested). Check third-party licenses (MediaPipe: Apache-2.0).
