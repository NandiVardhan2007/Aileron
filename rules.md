# RULES.md — Aileron

These rules bind every contributor, human or AI. Each rule has an ID so reviews and commits can cite it
(for example, "violates SAFE-03").

**Precedence when rules conflict:** Safety → Correctness → Latency → Features → Aesthetics.

---

## 1. Safety invariants (SAFE)

An input system that injects mouse and keyboard events can lock a user out of their own computer.
These rules exist to make that impossible.

- **SAFE-01 Kill switch.** A global hotkey (default `Ctrl+Alt+Esc`) must stop all output within one control tick. It is registered at the OS level and does not depend on camera, vision or gesture code.
- **SAFE-02 Neutral on loss.** If no valid hand frame arrives for `hand_lost_ms` (default 150 ms), release all held buttons and keys and return all gamepad axes and triggers to zero.
- **SAFE-03 No stuck inputs.** Every "press" has a guaranteed "release". On mode change, pause, exception, shutdown and signal (SIGINT, SIGTERM), the output layer calls `release_all()`. Use `try/finally` or context managers around every held state.
- **SAFE-04 Watchdog.** A watchdog thread checks the control loop heartbeat. If the loop stalls for more than 250 ms, it calls `release_all()` and flags a fault in the HUD.
- **SAFE-05 Arm before act.** The app starts **disarmed** (tracking visible, no output). Output begins only after an explicit arm action (the resume gesture or a hotkey).
- **SAFE-06 Clamp everything.** Cursor coordinates are clamped to the virtual desktop. Axes are clamped to `[-1, 1]`, triggers to `[0, 1]`. Scroll deltas per tick are capped.
- **SAFE-07 Rate limiting.** Click events are limited (default max 8 per second) and scroll and zoom events are capped per tick, so a vision glitch cannot spam the OS.
- **SAFE-08 Fail closed.** On any unhandled exception in the pipeline, the answer is: neutralize, disarm, log, show the fault. Never continue with partial state.
- **SAFE-09 Destructive gestures need confirmation.** No gesture may map to close-window, delete, shutdown or similar. If a user adds one, it requires a hold of at least 1 s and a HUD confirmation.
- **SAFE-10 Cockpit mode is separate.** Cockpit mode never emits mouse or keyboard events (except the explicit keyboard fallback), and Pointer mode never emits gamepad events.

---

## 2. Privacy (PRIV)

- **PRIV-01 Local only.** Camera frames and landmarks are processed on-device. No network calls in the pipeline.
- **PRIV-02 No frame persistence by default.** Video frames are never written to disk. Recording (`tools/record_session.py`) stores **landmarks only** (no pixels) and requires an explicit flag.
- **PRIV-03 Visible camera state.** The HUD always shows when the camera is active.
- **PRIV-04 No telemetry** without explicit opt-in. No analytics libraries.

---

## 3. Signal-processing rules (SIG)

- **SIG-01 Scale invariance.** All distances are divided by `palm_size` (defined in `agent.md` §2 and `docs/SIGNAL_PROCESSING.md`). Raw pixel or normalized-image distances may not be compared to thresholds.
- **SIG-02 Joint angles over coordinates.** Finger extension is computed from joint angles, not "tip.y < pip.y". This keeps it working when the hand is rotated or tilted.
- **SIG-03 Hysteresis on every binary decision.** Each gesture has separate `on` and `off` thresholds (for example pinch `on=0.25`, `off=0.35`). A single threshold is a bug.
- **SIG-04 Debounce by time.** A state change must hold for `min_hold_ms` before it fires. Holds that trigger mode actions use dwell timers with visible progress.
- **SIG-05 One Euro filter for pointer-like signals.** Use it for cursor and axis channels. Per-channel `min_cutoff` and `beta` are config values. Do not use fixed-window moving averages for cursor smoothing, because they add constant lag.
- **SIG-06 Freeze on click.** From pinch-down until release, cursor position is frozen (or heavily damped) to protect click accuracy. Drag unfreezes after the hold threshold.
- **SIG-07 Time-based, not frame-based.** All durations, velocities and filters use measured timestamps (`time.monotonic_ns`) and not frame counts, since camera FPS varies.
- **SIG-08 Handedness is user-relative.** Frames are mirrored once at capture; resolve handedness exactly once, in `vision/hands.py`.
- **SIG-09 Confidence gating.** Frames below `min_tracking_confidence` are treated as "no hand" for safety purposes (SAFE-02), not as degraded data.
- **SIG-10 Response curves are explicit.** Steering, throttle and scroll go through a named curve (`linear`, `expo(k)`) with deadzone and saturation parameters from config.
- **SIG-11 Sticky primary hand.** When several hands are visible, control locks to the hand that engaged first and only changes after it has been lost for `hand_lost_ms`; a second person in frame must never take over.

---

## 4. Gesture-design rules (GEST)

- **GEST-01 Natural default.** The resting hand state does nothing dangerous. "Engaged and open hand" only moves the cursor.
- **GEST-02 Distinct poses.** Two gestures may not differ only by a small threshold. If two poses share more than three finger states, they need a time or motion qualifier.
- **GEST-03 Fatigue budget.** No required pose may demand an arm raised above the shoulder for extended periods. Provide a rest pose and keep primary actions achievable with the elbow supported.
- **GEST-04 Feedback for every gesture.** Each recognized gesture gives immediate HUD feedback (icon, ring, color). Silent recognition is not allowed, because users cannot learn what they cannot see.
- **GEST-05 Reversible.** Any mode-changing or mode-arming gesture has an obvious inverse.
- **GEST-06 Accessible.** Support left-handed and right-handed use, adjustable dwell times, and a larger "sticky" mode for users with tremor (stronger filtering).
- **GEST-07 Documented before coded.** A gesture exists first as a row in `docs/GESTURES.md` with landmarks, thresholds and failure modes.
- **GEST-08 Calibration over constants.** Per-user ranges (finger extension min/max, steering range, neutral pose) come from the calibration profile, with defaults only as fallback.

---

## 5. Performance budgets (PERF)

Measured on the reference machine (documented in `docs/benchmarks.md`) with a 60 FPS, 720p camera.

| Metric | Budget |
|--------|--------|
| Glass-to-output latency, Pointer mode (p95) | ≤ 60 ms |
| Glass-to-output latency, Cockpit mode (p95) | ≤ 50 ms |
| Inference + processing per frame (p95) | ≤ 12 ms |
| Control loop tick jitter (p95) | ≤ 2 ms |
| CPU use, steady state | ≤ 25% of one modern core, excluding inference |
| Idle, no hand in view | Drop inference rate to save power |

- **PERF-01** Use a single-slot "latest frame" queue. Never queue frames. A stale frame is worse than a dropped frame.
- **PERF-02** No allocation-heavy work in the control tick (preallocate arrays, avoid per-frame object churn).
- **PERF-03** No blocking I/O, logging flushes or UI calls on the control thread.
- **PERF-04** Any PR touching the hot path includes before-and-after numbers from `tools/plot_latency.py`.

---

## 6. Code rules (CODE)

- **CODE-01** Python 3.11+, fully type-annotated, `mypy --strict` clean.
- **CODE-02** `ruff` for lint and format. No `# noqa` without a reason in the same comment.
- **CODE-03** Named landmark constants only (`Lm.INDEX_FINGER_TIP`), never bare indices.
- **CODE-04** No magic numbers in logic. Thresholds, timings and ranges live in `config/defaults.toml` and Pydantic models.
- **CODE-05** Gesture and filter code is **pure and deterministic**: input (features, timestamp) → output (events), with explicit state objects. No global state, no OS calls, no randomness.
- **CODE-06** Output backends implement one interface (`press`, `release`, `move`, `scroll`, `set_axis`, `set_trigger`, `release_all`). Logic never imports a concrete backend.
- **CODE-07** Platform-specific code lives only in `output/<platform>/` and is imported lazily.
- **CODE-08** Prefer dataclasses (`frozen=True, slots=True`) for frames, features and intents.
- **CODE-09** Errors are specific exceptions. No bare `except:`, and no swallowing exceptions in the control loop (see SAFE-08).
- **CODE-10** Dependencies are pinned in `uv.lock`. Adding a dependency needs a short justification in the PR.
- **CODE-11** Functions stay small and single-purpose. If a gesture state machine needs more than about 100 lines, split it.
- **CODE-12** Comments explain *why*. Names and types explain *what*.

---

## 7. Testing rules (TEST)

- **TEST-01** Every gesture has unit tests for: positive match, negative match, hysteresis (no flicker around the threshold), and debounce timing.
- **TEST-02** **Replay tests:** recorded landmark streams (`tests/replay/*.jsonl`) run through the full pipeline against the `null` backend, asserting the exact event sequence. Fixtures must include at least: slow motion, fast motion, partial occlusion, hand entering and leaving frame, and both handedness cases.
- **TEST-03** Safety tests are mandatory and may never be skipped: hand loss mid-drag, hand loss mid-throttle, mode switch while a button is held, exception in the pipeline, shutdown during drag. Each asserts `release_all()` was called and no input remains held.
- **TEST-04** Property tests (for example with Hypothesis): outputs are always within clamp ranges for arbitrary landmark input, including NaN, inf and degenerate hands (all points identical).
- **TEST-05** Filters are tested against known step and sine inputs for lag and overshoot.
- **TEST-06** Tests never require a camera or real OS input. Hardware tests live under `tests/manual/` and are excluded from CI.
- **TEST-07** A bug fix starts with a failing replay or unit test that reproduces it.

---

## 8. Configuration rules (CFG)

- **CFG-01** Layering: `defaults.toml` → user profile → CLI flags. Later layers override earlier ones.
- **CFG-02** Every config field has a type, a range validator and a docstring. Invalid config fails at startup with a clear message, never mid-session.
- **CFG-03** Profiles are versioned (`schema_version`) with migrations.
- **CFG-04** Changing a default threshold is a behavior change and needs a changelog entry.

---

## 9. Git and review rules (GIT)

- **GIT-01** Conventional Commits (`feat:`, `fix:`, `perf:`, `test:`, `docs:`, `refactor:`).
- **GIT-02** One logical change per PR. PR description states: what changed, which rule IDs it touches, how it was tested, and latency numbers if relevant.
- **GIT-03** No model binaries or recorded video in the repo. Landmark-only fixtures are allowed and kept small.
- **GIT-04** CI must pass: lint, type-check, unit and replay tests, safety tests.
- **GIT-05** Changes to `safety/` or any `SAFE-*` behavior need a second reviewer.

---

## 10. Forbidden

- Sending camera data or landmarks over a network.
- Writing video frames to disk by default.
- Bare landmark indices or hard-coded thresholds in logic.
- Gesture handlers that call OS APIs directly.
- Disabling, bypassing or "temporarily" skipping safety checks, including in tests or demos.
- Mapping any gesture to a destructive system action without SAFE-09 confirmation.
- Fixed-window averaging as the cursor smoother.
- Merging code that holds a button, key or axis without a guaranteed release path.
- Using the deprecated `mp.solutions.hands` API in new code.

---

## 11. Documentation rules (DOC)

- **DOC-01** Behavior changes update the matching file in `docs/` in the same PR.
- **DOC-02** Every non-obvious design choice gets an ADR in `docs/DECISIONS.md`.
- **DOC-03** Defaults in `config/defaults.toml` and `docs/CONFIGURATION.md` must match; CI checks this.
- **DOC-04** Gesture names, mode names and glossary terms follow `docs/BRANDING.md`.
