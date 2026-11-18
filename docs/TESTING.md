# Test Strategy — Aileron

Goal: be confident in gesture logic, filters and **especially safety behavior** without needing a camera or real OS
input in CI.

## 1. Test pyramid

| Layer | What | Tools | Runs in CI |
|-------|------|-------|-----------|
| Unit | Geometry, features, filters, FSMs, mapping, config validation | pytest | Yes |
| Property | Outputs stay in range for arbitrary/degenerate landmarks | hypothesis | Yes |
| Replay | Recorded landmark streams → full pipeline → exact events | pytest + `NullBackend` | Yes |
| Safety | Stuck-input, neutralization, kill switch, watchdog | pytest `-m safety` | Yes (mandatory) |
| Integration | Capture → tracker with a video-file fake source | pytest | Yes (small) |
| Performance | Latency, CPU, tick jitter benchmarks | `tools/plot_latency.py` | Nightly/optional |
| Manual / hardware | Camera, real OS input, real games | checklists | Pre-release |
| User studies | Fitts, lap time, fatigue, onboarding | protocols below | Per milestone |

## 2. Unit tests (examples)
- `palm_size` is invariant to hand translation and scales linearly with hand scale.
- `curl` returns ≈0 for a fist fixture and ≈1 for an open palm fixture, regardless of in-plane rotation.
- Pinch FSM: tap → CLICK; hold → DRAG_START/END; jitter around `on`/`off` → no flicker (hysteresis).
- One Euro: step response lag below target; jitter attenuation ≥ X dB on noise-only input.
- Steering: `θ=neutral` → 0; `θ=±steer_max` → ±1; deadzone and expo monotonic.
- Config: invalid ranges rejected with a clear message.

## 3. Property-based tests
Generate random landmark arrays including NaN/inf, collapsed hands (all points equal), huge values, missing hands,
and random timestamps (non-monotonic, large gaps). Assert: no exceptions escape the control tick, all intents within
clamp ranges, no `Button` held without a pending release.

## 4. Replay tests
**Fixtures** in `tests/replay/*.jsonl` (format in `INTERFACES.md` §8), recorded with `tools/record_session.py`
(landmarks only). Required scenarios:

| Fixture | Verifies |
|---------|----------|
| `move_slow`, `move_fast` | Cursor smoothing, no lag spikes |
| `pinch_click`, `pinch_drag`, `double_click` | G-02..G-04 timing |
| `right_click_vs_left` | Conflict resolution |
| `scroll_vsign` | G-07 deadzone/rate |
| `zoom_two_hand` | G-08 |
| `clutch_resume` | G-09/10 and state changes |
| `hand_exit_enter` | Neutralization and re-engage dwell |
| `occlusion_partial` | Confidence gating |
| `both_handedness` | Left/right mapping |
| `yoke_turns` | Steering curve and neutral |
| `trigger_ramp` | Throttle filter and deadzone |
| `two_people` | Primary-hand lock |

Each fixture may embed `expect` lines. Replays run at several simulated frame rates (30/60/90 fps) and with jittered timestamps.

## 5. Safety tests (`@pytest.mark.safety`, never skipped — `TEST-03`)

| Scenario | Assertion |
|----------|-----------|
| Hand lost mid-drag | `ButtonUp` emitted; ledger empty within `hand_lost_ms` + 1 tick |
| Hand lost mid-throttle | Trigger 0, steering 0 |
| Mode toggle while button held | `release_all` before switch |
| Exception injected into gesture engine | FAULT, disarmed, ledger empty |
| Control loop stall (sleep 400 ms) | Watchdog fires `release_all` |
| Kill switch during drag/throttle | Output stops within one tick |
| Shutdown (SIGINT/SIGTERM) | `release_all` called, backend closed |
| Event flood (mock generator) | Rate limiter caps output |
| Camera frames stop | Treated as hand lost |
| Backend raises on apply | Fallback `release_all`, FAULT |

## 6. Benchmarks and latency measurement
- **Software latency:** every message carries `t_capture_ns`; at emit, record `now − t_capture_ns`. Report p50/p95/p99.
- **Glass-to-glass (optional rig):** screen flash + photodiode, or high-speed phone video comparing a physical gesture with cursor motion.
- **Throughput:** FPS, dropped frames, inference time, CPU%.
- **Regression gate:** nightly job fails if p95 latency or CPU exceeds the budget by > 10%.
- Reference machine and camera are documented in `docs/benchmarks.md` (to be created in M0).

## 7. User study protocols

### 7.1 Pointing (ISO 9241-9 Fitts)
12+ participants, 3 conditions (Aileron, trackpad, mouse), multi-direction tapping task, 9 targets, 3 widths/amplitudes.
Metrics: throughput (bits/s), error rate, movement time, subjective effort (Borg CR10), NASA-TLX.
Target: throughput ≥ 2.0 bits/s.

### 7.2 Accidental actions
15-minute scripted desktop task (browse, scroll, drag files). Count unintended clicks/drags. Target ≤ 1 per 10 minutes.

### 7.3 Cockpit control quality
Reference track in an open-source racing sim. Compare Aileron (Yoke) vs gamepad: lap time, off-track events, steering smoothness
(RMS of steering rate). Include a throttle-strategy comparison (index extension vs thumb vs depth vs wrist twist), counter-balanced order.

### 7.4 Onboarding
Observe new users from install to first successful click; record time, errors, help requests. Target ≤ 5 min.

### 7.5 Diversity
Recruit varied skin tones, hand sizes, glasses/no glasses, lighting setups, both handedness, and at least a few users with tremor or limited mobility.

## 8. CI pipeline
1. Lint/format (`ruff`), type-check (`mypy --strict`)
2. Unit + property tests with coverage (gesture/safety modules ≥ 90%)
3. Replay tests
4. Safety suite (`-m safety`)
5. Docs/config consistency check (`defaults.toml` ↔ `CONFIGURATION.md`)
6. Build artifacts (nightly): packaging smoke test, benchmark job

## 9. Test data hygiene
Fixtures contain **landmarks only**, no images (`PRIV-02`). Participants sign consent for recorded landmark data; fixtures
are anonymized and small (< 1 MB each).
