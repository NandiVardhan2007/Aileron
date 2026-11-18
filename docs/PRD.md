# Product Requirements Document — Aileron

| | |
|---|---|
| Status | Draft v0.1 |
| Owner | Project lead |
| Last updated | 2026-11-18 |

## 1. Vision
Make any computer with a webcam controllable by hand motion alone: precise enough to replace a mouse for
everyday tasks, and expressive enough to steer a car, bike or aircraft in a simulator, with no extra hardware.

## 2. Problem
- Mice and gamepads require hardware; many people lack the right device at the right moment (presentations, kiosks, demos, hygiene-sensitive settings, desks without room).
- Existing webcam air-mouse tools are jittery, trigger accidental clicks, tire the arm, and have no real support for analog game control.
- People with limited fine-motor control or who cannot use a physical mouse need configurable, forgiving alternatives.

## 3. Target users

| Persona | Needs | Key requirements |
|---------|-------|------------------|
| **Sim enthusiast** ("Arjun") | Immersive steering and throttle without buying a wheel | Analog axes, low latency, virtual gamepad compatibility |
| **Presenter / teacher** | Control slides and pointer from a distance | Reliable click, scroll, standby (clutch), no accidents |
| **Accessibility user** | Mouse alternative with adjustable precision | Stronger smoothing, dwell options, left/right hand, large thresholds |
| **Maker / developer** | Hackable hand-tracking input platform | Plugin backends, replay tooling, clear contracts |

## 4. Use cases
- **UC-1** Browse and click with one hand across a room.
- **UC-2** Scroll long pages and zoom maps/photos/CAD views.
- **UC-3** Drive a racing game using a two-hand wheel gesture and trigger fingers.
- **UC-4** Ride a bike/motorbike sim using handlebar tilt.
- **UC-5** Pause tracking instantly (fist) to type or gesture at a person without moving the cursor.
- **UC-6** First-time user completes pre-flight calibration and makes a successful click in under 5 minutes.

## 5. Scope

**In scope (v1.0):** Pointer mode, Cockpit mode (Yoke + Handlebar), calibration, HUD, safety layer, profiles, Windows primary support, Linux best effort, macOS Pointer mode.
**Planned (post-1.0):** Stick (flight) profile, custom gesture editor, per-app profiles, macOS Cockpit via keyboard fallback polish, installer.
**Out of scope:** Eye/face tracking, full-body tracking, VR/AR headsets, cloud sync, mobile apps.

## 6. Functional requirements
Priority: **M** must, **S** should, **C** could.

### Pointer (FR-P)
| ID | Requirement | Pri |
|----|-------------|-----|
| FR-P1 | Move cursor from the hand anchor via a configurable active region mapped to the full virtual desktop (multi-monitor, DPI aware) | M |
| FR-P2 | Left click, double click, right click, middle click via pinch gestures | M |
| FR-P3 | Drag and drop via held pinch | M |
| FR-P4 | Scroll (vertical and horizontal) via V-sign with displacement-based rate | M |
| FR-P5 | Zoom via two-hand pinch spread (Ctrl+wheel) | S |
| FR-P6 | Clutch: fist pauses, open palm resumes | M |
| FR-P7 | Absolute and relative (trackpad-like) pointing modes | S |
| FR-P8 | Cursor freeze during click to protect accuracy | M |

### Cockpit (FR-C)
| ID | Requirement | Pri |
|----|-------------|-----|
| FR-C1 | Virtual gamepad output (analog left stick X, both triggers, buttons) | M |
| FR-C2 | Yoke profile: two-hand wheel angle → steering; index extension → throttle/brake | M |
| FR-C3 | Handlebar profile: hand roll → steering; configurable throttle source | S |
| FR-C4 | Pre-flight calibration of neutral, range and finger extension | M |
| FR-C5 | Adjustable deadzone, saturation, response curve per axis | M |
| FR-C6 | Gear up/down and extra buttons via pinch combos | S |
| FR-C7 | Keyboard fallback with PWM analog emulation | S |
| FR-C8 | Stick profile (pitch/roll/throttle) for flight sims | C |

### System (FR-S)
| ID | Requirement | Pri |
|----|-------------|-----|
| FR-S1 | Start disarmed; explicit arm | M |
| FR-S2 | Global kill-switch hotkey | M |
| FR-S3 | Neutralize and release all inputs on hand loss, fault, mode change, exit | M |
| FR-S4 | Mode switching via Shaka dwell gesture | M |
| FR-S5 | Per-user profiles, import/export (TOML) | S |
| FR-S6 | Record/replay of landmark streams for debugging | M |
| FR-S7 | Plugin entry points for gestures and output backends | C |
| FR-S8 | Opt-in black-box ring buffer (landmarks only) | C |

### UX (FR-U)
| ID | Requirement | Pri |
|----|-------------|-----|
| FR-U1 | HUD with tracking state, armed state, mode, gesture feedback, dwell rings | M |
| FR-U2 | Tray icon with mode/state, quick pause, quit | S |
| FR-U3 | Guided onboarding and calibration wizard | M |
| FR-U4 | Left-handed, right-handed and "either" support | M |
| FR-U5 | Accessibility options: stronger smoothing, longer dwell, larger targets | S |

## 7. Non-functional requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Glass-to-output latency, Pointer (p95) | ≤ 60 ms |
| NFR-2 | Glass-to-output latency, Cockpit (p95) | ≤ 50 ms |
| NFR-3 | CPU use steady state (excluding inference) | ≤ 25% of one core |
| NFR-4 | Hand-lost neutralization | ≤ 150 ms (+1 tick) |
| NFR-5 | Kill switch response | ≤ 1 control tick (~8 ms) |
| NFR-6 | Privacy | No network use in the pipeline; no frames on disk |
| NFR-7 | Robustness | Works in normal indoor lighting, varied skin tones, with glasses; degrades gracefully in low light |
| NFR-8 | Portability | Windows 10/11, Ubuntu 22.04+ (X11), macOS 13+ |
| NFR-9 | Startup time | ≤ 3 s to live preview |
| NFR-10 | Accessibility | All dwell times and thresholds adjustable |

## 8. Success metrics

| Metric | Target | How measured |
|--------|--------|--------------|
| Pointing throughput (ISO 9241-9 Fitts test) | ≥ 2.0 bits/s | `tools/fitts_test.py` with 12 users |
| Accidental clicks | ≤ 1 per 10 min of normal use | Replay + live study |
| Missed intended clicks | ≤ 5% | Live study |
| Cockpit control quality | Reference lap within 120% of gamepad baseline | Timed lap study |
| Time to first successful click (new user) | ≤ 5 min | Onboarding study |
| Arm fatigue | Self-reported ≤ 5/10 after 15 min | Borg CR10 survey |
| Crash-free sessions | ≥ 99% | Beta telemetry (opt-in) or manual logs |

## 9. Constraints and assumptions
- A single RGB webcam is the only required sensor; 720p/30 fps minimum.
- One primary user in view; a second person in the frame must not hijack control (largest/closest-hand lock).
- Users can install a virtual-gamepad driver on Windows (needs admin rights).
- MediaPipe model files are downloaded at first run or bundled.

## 10. Risks

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| R1 | Jitter and latency make pointing frustrating | High | High | One Euro filters, active region tuning, 60 fps cameras, latency benchmarks in CI |
| R2 | Accidental actions (Midas touch) | High | High | Disarmed start, clutch, hysteresis, dwell, click freeze |
| R3 | Arm fatigue ("gorilla arm") | High | Medium | Small active region, rest pose, elbow-supported design, fatigue reminders |
| R4 | Virtual-gamepad driver ecosystem changes (ViGEmBus is reported as no longer maintained; verify current status) | Medium | High | Backend abstraction; evaluate vJoy / custom driver / keyboard fallback early |
| R5 | Single-camera depth/rotation is noisy (throttle by wrist twist) | Medium | Medium | Prototype with user testing; default to index-extension throttle |
| R6 | Lighting, skin tone and occlusion bias in tracking | Medium | High | Diverse test set, confidence gating, low-light guidance in HUD |
| R7 | Anti-cheat systems flag virtual input drivers in online games | Medium | Medium | Document; recommend offline/single-player; no injection into game processes |
| R8 | OS permission friction (camera, accessibility, input monitoring) | Medium | Medium | Guided permission flow in onboarding |
| R9 | Python performance ceiling | Low | Medium | Profile first; hot path can move to Rust/C++ behind the same interfaces |
| R10 | Name/trademark conflict | Medium | Low | Check before launch; shortlist in `BRANDING.md` |

## 11. Release criteria (v1.0)
- All **M** requirements implemented and tested; safety suite green.
- Latency and CPU budgets met on the reference machine.
- Onboarding, Fitts and lap studies completed with targets met or documented gaps.
- Docs complete; installer for Windows; known issues listed.
