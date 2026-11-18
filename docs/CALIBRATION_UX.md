# Calibration and UX — Aileron

## 1. Principles
- A first success within minutes beats a perfect setup (target: first click ≤ 5 min).
- Always show what the system sees (skeleton overlay) and what it understood (gesture feedback).
- Never require a gesture the user has not been shown and practiced.
- Everything can be undone or skipped; defaults must be usable without calibration.

## 2. Onboarding flow

| Step | Screen | Checks |
|------|--------|--------|
| 1 | Welcome + privacy statement ("video never leaves this computer") | Camera permission |
| 2 | **Camera check:** live preview, lighting meter, framing guide | Resolution/FPS, brightness, backlight warning |
| 3 | **Handedness check:** "Raise your right hand" | Verifies side mapping (`SIG-08`) |
| 4 | **Pre-flight (Pointer):** open hand range of motion; corners of the active region | Sets `region_*` |
| 5 | **Practice:** pinch to click a target, drag a card, scroll a list | Tunes `pinch_on/off` from the user's own min/max |
| 6 | **Safety briefing:** clutch (fist), arm (palm), kill switch hotkey | User must perform each once |
| 7 | Optional: **Pre-flight (Cockpit)** | See §3 |
| 8 | Summary + save profile | |

## 3. Cockpit pre-flight

1. **Neutral:** "Hold your hands as if gripping a wheel, level." Capture 2 s → `θ_neutral` (Yoke) / `roll_neutral` (Handlebar).
2. **Lock-to-lock:** "Turn left as far as comfortable, then right." → `steer_max` (clamped to 25–60°).
3. **Throttle finger:** "Curl, then straighten your right index finger." → `ext_min/ext_max` (three repeats, take the median).
4. **Brake finger:** same for the left hand.
5. **Live test:** steering arc, throttle and brake bars, gear/button indicators; user confirms the feel.
6. **Optional game test:** `--gamepad-test` page or Windows "Game Controllers" panel.

Each step shows a countdown ring, rejects unstable captures (variance too high), and allows retry.

## 4. HUD design

| Element | Description |
|---------|-------------|
| Skeleton overlay | 21-point hand drawn thin; colour = state (green tracking, amber low confidence, grey lost) |
| State chip | `DISARMED` / `ARMED` / `STANDBY` / `FAULT` with colour |
| Mode chip | `POINTER` or `COCKPIT · YOKE` |
| Dwell ring | Circular progress around the fingertip/palm for held gestures |
| Cursor halo | Shrinks while pinching, fills while dragging |
| Cockpit panel | Steering arc, throttle (green) and brake (red) bars, gear indicator |
| Debug panel (toggle) | FPS, inference ms, latency p50/p95, hand confidence, event log |
| Toasts | Short messages: "Move closer", "Low light", "Inputs released" |

- HUD is a click-through, always-on-top transparent window; it must never steal focus or receive input.
- Compact mode: small corner widget; Full mode: calibration and debugging.
- Respects OS dark/light, reduced motion, and DPI scaling.
- No flashing faster than 3 Hz (`SAFETY H13`).

## 5. Accessibility
- **Stability mode:** stronger smoothing, larger pinch thresholds, longer dwell times (tremor support).
- **One-handed everything** in Pointer mode; left/right-only option.
- **Dwell click** option (hover to click) for users who cannot pinch.
- Adjustable HUD size and contrast; optional audio cues; keyboard shortcuts for all HUD actions.
- All timing values user-configurable (`GEST-06`).

## 6. Error and guidance messages

| Situation | Message (tone: calm, actionable) |
|-----------|----------------------------------|
| No hand | "I can't see your hand. Raise it into view." |
| Too far | "Move your hand a little closer." |
| Low light | "It's quite dark. Turn on a light in front of you." |
| Backlit | "A bright window behind you makes tracking harder. Try turning around or closing the blind." |
| Camera busy | "Another app is using the camera. Close it and retry." |
| Gamepad driver missing | "Cockpit mode needs a virtual controller driver. Install it, or use keyboard fallback." |
| Fault | "Something went wrong. All inputs were released. You are disarmed." |

## 7. Settings structure
General (start with OS, camera device, resolution/FPS) · Pointer (region, gain, relative/absolute, scroll, click timings) ·
Cockpit (profile, axes shaping, throttle source, on-loss behavior) · Gestures (enable/disable, bindings, dwell) ·
Accessibility · Safety (hotkeys, rate limits) · Advanced (filters, logging, black box).

## 8. Microcopy and naming
Follow `BRANDING.md`: "Pre-flight", "Armed/Disarmed", "Standby", "Cockpit", "Kill switch". Keep aviation flavor light in
the UI; clarity beats theme in safety-critical messages.
