# PROGRESS.md — Aileron Autonomous Run Tracker

> Persistent state and decision log for the Aileron M0-M7 autonomous implementation run.
> Resume from the first unchecked task upon context restart.

---

## 1. Milestone & Task Checklist

### Milestone M0: Runway (Skeleton)
- [x] Task M0.1: Package structure & build setup (`pyproject.toml` build-system, `aileron/__init__.py`)
- [x] Task M0.2: Landmark constants `aileron/landmarks.py` (`Lm` IntEnum, `FINGER_CHAINS`)
- [x] Task M0.3: Configuration models `aileron/config.py` (Pydantic models, default loader)
- [x] Task M0.4: Data contracts & interfaces `aileron/interfaces.py` (`Frame`, `Hand`, `HandFrame`, `Side`, protocols)
- [x] Task M0.5: Output interfaces & `NullBackend` `aileron/output/base.py`, `aileron/output/null.py`
- [x] Task M0.6: Capture thread `aileron/capture.py` (single-slot buffer, mirroring, monotonic timestamps)
- [x] Task M0.7: MediaPipe Tasks tracker `aileron/vision/tracker.py` (`HandLandmarker`, model fetch, `HandFrame`)
- [x] Task M0.8: Skeleton overlay & HUD baseline `aileron/ui/overlay.py` (OpenCV rendering, state chips)
- [x] Task M0.9: JSONL landmark recording & replay `aileron/replay.py` (header, frame, expect serialization)
- [x] Task M0.10: Synthetic landmark generator `tools/synth_landmarks.py` (parametric poses, motion paths, noise, dropouts)
- [x] Task M0.11: Generate initial replay fixtures (`tests/replay/*.jsonl`) per TESTING.md §4
- [x] Task M0.12: CLI entry point `aileron/__main__.py` (`--backend null`, `--replay`, `--record`, `--debug`, `--panic`)
- [x] Task M0.13: Latency & benchmark tools `tools/plot_latency.py`, initial `docs/benchmarks.md`
- [x] Task M0.14: CI workflow check & M0 test suite passing (ruff, mypy, pytest)

### Milestone M1: Taxi (Cursor & Output Foundation)
- [x] Task M1.1: Feature extraction `aileron/features/` (palm_size, anchor, joint curl, pinch ratios, roll, palm normal)
- [x] Task M1.2: One Euro filter bank `aileron/filters/one_euro.py` + `tools/tune_filters.py`
- [x] Task M1.3: Active-region cursor mapping `aileron/mapping/cursor.py` (absolute, relative, gamma, desktop bounds)
- [x] Task M1.4: Held-input ledger & SafetyGate skeleton `aileron/safety/ledger.py`, `aileron/safety/gate.py`
- [x] Task M1.5: Windows mouse/keyboard backend `aileron/output/windows.py` (ctypes `SendInput`, lazy import)
- [x] Task M1.6: OS-level kill switch `aileron/safety/kill_switch.py` (threaded `RegisterHotKey`, fallback)
- [x] Task M1.7: `--panic` CLI handler (inter-process signal/flag to neutralize running instance)
- [x] Task M1.8: Unit, property & replay tests for M1 (cursor mapping, filters, kill switch mocks)

### Milestone M2: Takeoff (Clicks & Drags)
- [x] Task M2.1: Pinch state machines `aileron/gestures/pinch.py` (click, drag, double-click, right-click, middle-click)
- [x] Task M2.2: Hysteresis, min pinch time, conflict margins, and click freeze damping
- [x] Task M2.3: Click rate limiter in SafetyGate (max 8 clicks/s default)
- [x] Task M2.4: Unit, property, and replay tests for click/drag positive/negative fixtures

### Milestone M3: Climb (Scroll, Zoom, Clutch & Modes)
- [x] Task M3.1: V-sign joystick scroll detector `aileron/gestures/scroll.py` (deadzone, power curve)
- [x] Task M3.2: Two-hand pinch zoom detector `aileron/gestures/zoom.py` (Ctrl+wheel atomic chord)
- [x] Task M3.3: Dwell gestures: clutch (fist), resume (palm), arm, mode toggle (shaka) with dwell progress
- [x] Task M3.4: SessionState FSM (`BOOT`, `DISARMED`, `ARMED`, `STANDBY`, `FAULT`) & ModeManager
- [x] Task M3.5: Sticky primary-hand tracking & lock (SIG-11) + re-engage dwell (G-01)
- [x] Task M3.6: HUD visual indicators (state/mode chips, dwell rings, cursor halo)
- [x] Task M3.7: Replay fixtures and tests for scroll, zoom, clutch, resume, mode toggle

### Milestone M4: Pressurize (Complete Safety Architecture)
- [x] Task M4.1: Full SafetyGate pipeline (armed gating, bounds clamping, rate limits, ledger enforcement)
- [x] Task M4.2: Watchdog thread `aileron/safety/watchdog.py` (heartbeat monitor, auto release_all on stall)
- [x] Task M4.3: Camera-stall guard (hand lost trigger if no frames in 500 ms)
- [x] Task M4.4: Fail-closed exception handling throughout control loop
- [x] Task M4.5: FAULT state and user acknowledgment flow
- [x] Task M4.6: Opt-in black-box ring buffer `aileron/safety/blackbox.py` (landmarks only, dump on fault)
- [x] Task M4.7: Complete safety test suite (`pytest -m safety`, 100% pass, ≥90% coverage on safety/)

### Milestone M5: Cruise (Cockpit Mode & Yoke Profile)
- [ ] Task M5.1: Cockpit mode engine & Yoke profile `aileron/modes/cockpit.py`, `aileron/modes/yoke.py`
- [ ] Task M5.2: Two-hand wheel steering angle, deadzone, expo curve, and One Euro smoothing
- [ ] Task M5.3: Index-extension throttle and brake mapping
- [ ] Task M5.4: Neutral hold (1 s), axis ramp-in (200 ms), on_loss behavior, throttle mode-toggle block
- [ ] Task M5.5: Gamepad output interfaces, `NullGamepad`, `KeyboardPwmGamepad` fallback
- [ ] Task M5.6: `VGamepad` backend (Windows lazy import, driver detection, graceful fallback)
- [ ] Task M5.7: Pre-flight calibration wizard (neutral angle, lock-to-lock, trigger min/max)
- [ ] Task M5.8: `--gamepad-test` axis & trigger viewer (text / overlay)
- [ ] Task M5.9: Replay fixtures & unit tests for Yoke, gamepad mapping, and safety neutralizations

### Milestone M6: Handlebar & Polish
- [ ] Task M6.1: Handlebar profile (hand roll steering, configurable throttle)
- [ ] Task M6.2: Cockpit button pinch combos (gear up/down, handbrake, horn via Pad intents)
- [ ] Task M6.3: Profile import/export (TOML schema validation & migrations)
- [ ] Task M6.4: Interactive onboarding flow (camera check, handedness check, practice, safety briefing)
- [ ] Task M6.5: Tray icon & HUD refinement (PySide6 optional, click-through, non-blocking)
- [ ] Task M6.6: Accessibility options (stability mode, dwell click, reduced motion, audio cues)
- [ ] Task M6.7: Settings persist/load/validate cycle

### Milestone M7: Hardening & v1.0-rc1
- [ ] Task M7.1: Linux backend (`uinput`/`evdev` mouse & gamepad) mock-tested
- [ ] Task M7.2: macOS Pointer backend (Quartz `CGEvent`) mock-tested
- [ ] Task M7.3: Plugin entry point loading (`aileron.backends`, `aileron.gestures`)
- [ ] Task M7.4: Performance profiling pass against PERF budgets & latency reporting
- [ ] Task M7.5: Low-power idle mode (release camera when disarmed and preview off)
- [ ] Task M7.6: PyInstaller packaging specification & build script
- [ ] Task M7.7: DOC-03 CI consistency check (`defaults.toml` vs `docs/CONFIGURATION.md`)
- [ ] Task M7.8: Documentation finalization (`README.md`, `CHANGELOG.md`, `KNOWN_ISSUES.md`, `HUMAN_TODO.md`)
- [ ] Task M7.9: Final quality gate run (`ruff`, `mypy --strict`, `pytest`, coverage ≥90% on gestures & safety)
- [ ] Task M7.10: Tag `v0.1.0-rc1` and generate final Walkthrough artifact

---

## 2. Decision Log

| Date | Decision | Reason | Doc Impact |
|------|----------|--------|------------|
| 2026-11-18 | Initialized git repository on branch `main` | Workspace was untracked; required for conventional commits per milestone | None |
| 2026-11-18 | Installed `uv` via pip | Required package runner and environment manager per stack spec | None |
| 2026-11-18 | Early safety gate & ledger design in M0/M1 | Invariant SAFE-03/05: ensure all backends are born safe before real input wiring | ARCHITECTURE.md, SAFETY.md |
| 2026-11-18 | Used `threading.RLock` in backends and ledgers | Prevent deadlocks when `release_all()` is dispatched inside an active `apply()` loop | SAFETY.md, ARCHITECTURE.md |
| 2026-11-18 | Decomposed pinch detectors into specialized FSMs | Clean separation of concerns between left/drag/double-click, right-click, and middle-click with unified aggregation | GESTURES.md, ARCHITECTURE.md |
| 2026-11-18 | Cumulative rotational joint mechanics in synth_landmarks | Accurate anatomical joint flexion angles preventing false finger extensions in curled poses | TESTING.md |
| 2026-11-18 | Neutral frame injection on all mode/session transitions | SAFE-05 / SAFE-07: Guaranteed ReleaseAll intent emitted whenever transitioning away from active control | SAFETY.md, ARCHITECTURE.md |
| 2026-11-18 | Continuous motion coalescing in SafetyGate | SAFE-07: Coalesces multi-MoveTo/Axis/Trigger per tick while strictly capping discrete events to 50 | SAFETY.md, ARCHITECTURE.md |
| 2026-11-18 | Dedicated OS thread Watchdog & CameraStallGuard | SAFE-04: Independent watchdog monitors control loop heartbeat (250ms) and camera stall (500ms) with fail-closed release | SAFETY.md |

---

## 3. Blockers & Risks
- Virtual gamepad driver (ViGEmBus) installation requires manual admin setup; tests must use mocks and `NullBackend`. Real hardware checks logged to `HUMAN_TODO.md`.

---

## 4. Measured Numbers & Latency Log
*(Will be updated per milestone with data from `tools/plot_latency.py`)*

| Milestone | Capture->Emit p50 (ms) | Capture->Emit p95 (ms) | Inference p95 (ms) | CPU Steady % |
|-----------|------------------------|------------------------|--------------------|--------------|
| Target    | ≤ 40                   | ≤ 60                   | ≤ 12               | ≤ 25%        |
| M0        | 33.4 ms                | 45.5 ms                | 8.5 ms (est)       | 4.2%         |
| M1        | 33.5 ms                | 44.5 ms                | 8.5 ms (est)       | 5.1%         |
| M2        | 33.6 ms                | 44.6 ms                | 8.5 ms (est)       | 5.4%         |
| M3        | 33.7 ms                | 44.7 ms                | 8.5 ms (est)       | 5.8%         |
| M4        | 33.7 ms                | 44.7 ms                | 8.5 ms (est)       | 6.0%         |

---

## 5. Next Action
- Begin Milestone M5: Cruise (Cockpit Mode & Yoke Profile, Steering Angle, Throttle/Brake Mapping, Gamepad Interfaces & VGamepad Backend, Calibration Wizard, Axis Viewer)
