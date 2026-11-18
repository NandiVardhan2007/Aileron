# Gesture Specification — Aileron

Gestures are defined **before** they are coded (`GEST-07`). Thresholds are defaults from
`config/defaults.toml`; math is in `SIGNAL_PROCESSING.md`. Finger states: **E** extended, **C** curled,
**–** don't care.

## 1. Finger-state notation

| Pose | Thumb | Index | Middle | Ring | Pinky | Extra |
|------|:-----:|:-----:|:------:|:----:|:-----:|-------|
| Open palm | E | E | E | E | E | fingers spread ok |
| Fist | C | C | C | C | C | |
| V-sign | – | E | E | C | C | index–middle gap > 0.3 palm |
| Shaka | E | C | C | C | E | |
| Pinch-index | tip near | tip near | – | – | – | `pinch_index < on` |
| Pinch-middle | tip near | – | tip near | – | – | `pinch_middle < on`, index not pinching |
| Pinch-ring | tip near | – | – | tip near | – | `pinch_ring < on` |

## 2. Pointer mode

| ID | Gesture | Trigger | Output | Timing | Failure modes / notes |
|----|---------|---------|--------|--------|-----------------------|
| G-01 | **Engage / move** | Valid hand present for `engage_ms=300` | Cursor follows anchor (`SIGNAL §4`) | — | Hand entering the frame must not move the cursor until engaged |
| G-02 | **Left click** | Pinch-index on then off | `Click(LEFT)` | on→off < `tap_ms=300` | Fast pinch can look like noise → confidence gating + min pinch duration `40 ms` |
| G-03 | **Drag** | Pinch-index held ≥ `tap_ms` | `ButtonDown(LEFT)` … `ButtonUp(LEFT)` | release on pinch-off or hand loss | Always release on hand loss (`SAFE-02`) |
| G-04 | **Double click** | Two taps within `dbl_ms=350` | `Click(LEFT, 2)` | | Cursor stays frozen between taps |
| G-05 | **Right click** | Pinch-middle tap | `Click(RIGHT)` | `tap_ms` | Must not fire if pinch-index is also on |
| G-06 | **Middle click** | Pinch-ring tap | `Click(MIDDLE)` | `tap_ms` | Ring/pinky coupling → needs ring `ext` drop-out check |
| G-07 | **Scroll** | V-sign held `120 ms` | `Scroll` rate from displacement | ends when pose lost | Cursor frozen while scrolling; pose flicker handled by hysteresis |
| G-08 | **Zoom** | Both hands pinch-index | `Zoom(±n)` | start when both pinch ≥ `80 ms` | Distinguish from two independent clicks: zoom needs both hands pinching simultaneously |
| G-09 | **Standby (clutch)** | Fist held `clutch_ms=400` | State → STANDBY, cursor frozen, buttons released | | Fist with a drag in progress: release first |
| G-10 | **Resume** | Open palm held `resume_ms=400` while STANDBY | State → ARMED | | Palm must face the camera (palm-normal z) |
| G-11 | **Mode toggle** | Shaka held `mode_ms=800` | POINTER ↔ COCKPIT | ring on HUD; cancel by changing pose | Not available while dragging |
| G-12 | **Arm** | Open palm held `arm_ms=800` while DISARMED | State → ARMED | | Alternative: hotkey |

### Conflict matrix (what could be mistaken for what)

| A | B | Why confusable | Resolution |
|---|---|----------------|-----------|
| Pinch-index | Pinch-middle | Shared thumb, adjacent fingers | Take the smaller ratio; require margin ≥ 0.08 palm |
| V-sign | Pinch-middle | Middle extended in both | V-sign requires thumb tip far (> 0.5 palm) from index/middle tips |
| Fist | Closed pinch | Both mostly curled | Fist requires **all** four fingers curled and pinch ratio > 0.5 |
| Open palm | Moving hand | Default engage state | Resume gesture only recognized in STANDBY/DISARMED |
| Shaka | Thumb-up/other | Thumb+pinky | Require index/middle/ring curled and dwell 800 ms |

### Hysteresis defaults

| Signal | On | Off |
|--------|----|-----|
| Pinch ratio | 0.25 | 0.35 |
| Finger extension | 0.75 | 0.35 |
| V-sign gap | 0.30 | 0.20 |
| Palm facing camera (normal·z) | 0.60 | 0.40 |

## 3. Cockpit mode (inputs, not discrete gestures)

Cockpit control is mostly **continuous** (see `COCKPIT_MODE.md` and `SIGNAL_PROCESSING.md` §8–10). Discrete
actions available there:

| ID | Gesture | Action |
|----|---------|--------|
| G-21 | Right pinch thumb+ring (tap) | Gear up (`RB`) |
| G-22 | Left pinch thumb+ring (tap) | Gear down (`LB`) |
| G-23 | Right pinch thumb+pinky (tap) | Handbrake / `X` (configurable) |
| G-24 | Left pinch thumb+pinky (tap) | Horn / reset / `Y` (configurable) |
| G-25 | Shaka dwell (either hand) | Back to Pointer mode |
| G-26 | Both hands open palm, hold 1 s | Pause output (neutral) |

## 4. Feedback requirements (`GEST-04`)

| Event | HUD feedback | Audio (optional) |
|-------|--------------|------------------|
| Hand found / lost | Skeleton overlay turns green / amber | soft tick / none |
| Pinch pending | Fingertip glow, cursor ring shrinks | — |
| Click | Ripple at the cursor | click tick |
| Drag active | Cursor ring locked/filled | low hum (optional) |
| Dwell gestures | Progress ring (0–100%) | — |
| Standby | Dimmed HUD, "STANDBY" label | down-tone |
| Mode change | Mode banner (2 s) | two-tone |
| Fault | Red banner, "inputs released" | alarm tone |

## 5. Handedness and customization
- Default: **either hand**; the first hand to engage becomes the primary. Left/right-only options in settings.
- All gesture→action bindings, dwell times and thresholds are overridable in the user profile.
- Custom gesture editor (post-1.0): record a pose, choose finger-state constraints, bind an action; the editor
  validates against the conflict matrix automatically.

## 6. Ergonomics guidance
- Keep the elbow supported; the active region defaults to ~60% × 50% of the frame so small motions cover the screen.
- Recommended camera at eye level or slightly below; avoid backlighting.
- Take a micro-break every 10–15 minutes; the HUD can remind you (`fatigue_reminder_min`).
- Prefer pinch gestures over wide finger spreads to reduce tendon strain.
