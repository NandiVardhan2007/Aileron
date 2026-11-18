# Architecture Decision Records — Aileron

Format: **Context → Decision → Consequences → Status**.

---
## ADR-001 — Python + MediaPipe Tasks for v1
**Context:** Need rapid iteration, strong CV ecosystem, easy hand-landmark model access.
**Decision:** Python 3.11+, MediaPipe Tasks `HandLandmarker` (LIVE_STREAM), OpenCV capture.
**Consequences:** Fast development; Python overhead in the control loop is acceptable at 120 Hz with NumPy. Hot path can be ported to Rust/C++ behind the same interfaces if profiling demands. Legacy `mp.solutions.hands` is not used.
**Status:** Accepted.

## ADR-002 — Unidirectional pipeline with immutable messages
**Context:** Hand-tracking apps become tangled when gesture code calls OS APIs directly.
**Decision:** Capture → Tracker → Features → Filters → Gestures → Mode → Mapper → Safety → Backend, passing frozen dataclasses.
**Consequences:** Every stage replayable and testable offline; backends swappable; slight overhead from object creation (mitigated with `slots`).
**Status:** Accepted.

## ADR-003 — Cursor anchored at knuckles (landmarks 5 & 9), not fingertip
**Context:** Pinching moves the fingertips and nudges the cursor, so clicks land off-target.
**Decision:** Anchor = midpoint(INDEX_MCP, MIDDLE_MCP); additionally freeze the cursor during pinch-pending.
**Consequences:** Stable clicks; slightly less "pointing" feel than a fingertip cursor. Fingertip pointing may be an optional mode.
**Status:** Accepted.

## ADR-004 — One Euro filter instead of moving average
**Context:** Need low jitter when still and low lag when fast.
**Decision:** One Euro filter per channel with per-channel parameters.
**Consequences:** Two parameters to tune per channel; tooling (`tune_filters.py`) provided. Moving averages forbidden for the cursor (`SIG-05`).
**Status:** Accepted.

## ADR-005 — Virtual gamepad for Cockpit mode, with keyboard fallback
**Context:** Simulators need analog inputs; keyboards are binary.
**Decision:** Primary output is a virtual Xbox-style gamepad; keyboard PWM is a fallback.
**Consequences:** Depends on platform drivers (Windows needs a virtual-gamepad driver; the ViGEm ecosystem is reported as unmaintained — verify and keep abstraction); macOS limited to fallback. Backend interface isolates the risk.
**Status:** Accepted, with an early spike to validate the driver choice.

## ADR-006 — Start disarmed; clutch gesture; global kill switch
**Context:** Always-on gesture control suffers from the "Midas touch" problem and can cause harm if it misfires.
**Decision:** Disarmed start, explicit arm, fist clutch, OS-level kill switch independent of vision, watchdog.
**Consequences:** Slightly more friction at start (mitigated by onboarding); strong safety story.
**Status:** Accepted.

## ADR-007 — Displacement-based (joystick) scrolling
**Context:** Swipe-based scrolling needs repeated motions and fatigues the arm.
**Decision:** V-sign sets an anchor; displacement from the anchor controls scroll rate with a deadzone and power curve.
**Consequences:** Continuous, controllable scrolling; needs good deadzone tuning to avoid drift.
**Status:** Accepted.

## ADR-008 — Index-finger extension as default throttle/brake
**Context:** Throttle must be analog, low-lag, and independent of steering.
**Decision:** Default: right index = throttle, left index = brake; alternatives behind config and evaluated in user studies.
**Consequences:** Pedals decoupled from wheel angle; relies on finger visibility. May change based on study results (ADR amendment required).
**Status:** Provisional.

## ADR-009 — World landmarks for angles; image landmarks for screen mapping
**Context:** 2D angles are distorted by foreshortening.
**Decision:** Compute joint angles, roll and palm normal from MediaPipe world landmarks; use normalized image landmarks for on-screen position.
**Consequences:** More robust to hand tilt; world-landmark depth is still estimated (noisy) so filters and calibration remain necessary.
**Status:** Accepted.

## ADR-010 — Landmark-only recording and local-only processing
**Context:** Camera data is sensitive.
**Decision:** No frames on disk, no network in the pipeline; recordings and the black box store landmarks only and are opt-in.
**Consequences:** Debugging relies on landmark replays; some visual bugs harder to reproduce (accepted).
**Status:** Accepted.

## ADR-011 — Mirror once at capture
**Context:** Mirroring in multiple places causes left/right bugs.
**Decision:** Mirror the frame once in the capture stage; all downstream coordinates are in the user's view. Handedness is verified in onboarding ("raise your right hand").
**Consequences:** Single source of truth for orientation; recordings are mirrored (flagged in the header).
**Status:** Accepted.

## ADR-012 — Fixed-rate control loop decoupled from camera rate
**Context:** Camera FPS varies and jitters; output should be steady.
**Decision:** Control loop ticks at `tick_hz` (default 120), consuming the newest frame; no extrapolation of motion.
**Consequences:** Smooth output cadence and consistent timers; up to one tick of added latency (≤ ~8 ms), accounted for in the budget.
**Status:** Accepted.
