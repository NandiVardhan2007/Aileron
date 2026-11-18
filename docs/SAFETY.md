# Safety, Reliability and Privacy — Aileron

Aileron injects input into the user's computer. A fault can click on the wrong thing, hold a key down,
or leave a virtual gamepad at full throttle. This document is the hazard analysis behind the `SAFE-*` rules.

## 1. Safety principles
1. **Fail closed.** Any doubt → release everything and stop output.
2. **Independent last line of defense.** The kill switch and watchdog do not depend on the vision pipeline.
3. **No surprises.** Start disarmed; announce every state change; ramp in analog outputs.
4. **Everything pressed is released.** A ledger tracks held inputs; shutdown, faults and mode changes drain it.

## 2. Hazard analysis

| ID | Hazard | Cause | Severity | Mitigation | Rule |
|----|--------|-------|----------|-----------|------|
| H1 | Stuck mouse button / drag | Hand lost mid-drag; crash | High | Release on hand loss; ledger; `try/finally`; watchdog | SAFE-02/03/04 |
| H2 | Stuck key (e.g., Ctrl during zoom) | Exception between down/up | High | Ledger + `release_all()`; Zoom emitted as atomic chord | SAFE-03 |
| H3 | Runaway throttle/steering | Frozen last value; tracking lost | High | Neutral on loss; ramp-in; stall watchdog | SAFE-02/04 |
| H4 | Accidental click on destructive UI | False pinch; Midas touch | High | Hysteresis, click rate limit, clutch, freeze-on-click, no destructive gestures | SAFE-07/09, SIG-03 |
| H5 | Cursor lost off-screen / unusable | Mapping bug | Medium | Clamp to desktop; kill switch; keyboard unaffected | SAFE-06 |
| H6 | Output after the user wanted stop | Gesture misread; hotkey blocked | High | OS-level hotkey independent of vision; also tray "Pause" | SAFE-01 |
| H7 | Second person/background hand hijacks control | Multiple hands | Medium | Sticky primary hand; require engage dwell | SIG-11, G-01 |
| H8 | Unintended mode switch at speed | Shaka misdetected | Medium | 0.8 s dwell; ignored when throttle > 0.3 | G-11 |
| H9 | Event flood freezes OS UI | Bug producing thousands of events | High | Rate limiting; per-tick caps; backend queue limits | SAFE-07 |
| H10 | Privacy leak of camera feed | Logging/recording/telemetry | High | No frame persistence; local only; visible camera indicator; opt-in black box (landmarks only) | PRIV-* |
| H11 | Malicious plugin | Third-party code | Medium | Plugins are trusted local code only, documented, no auto-download | ARCH §11 |
| H12 | Physical strain / fatigue | Prolonged mid-air use | Medium | Rest pose, ergonomic defaults, break reminders | GEST-03 |
| H13 | Photosensitive discomfort from HUD flashing | Flashing overlays | Low | No flashing > 3 Hz; reduced-motion setting | UX |

## 3. Kill switch design
- Registered with the OS (`RegisterHotKey` on Windows, X11 grab or evdev on Linux, `CGEventTap` on macOS).
- Runs on its own thread with no dependency on capture, MediaPipe or the control loop.
- Action: set `armed=False`, call `backend.release_all()` directly (bypassing the gate), show the HUD banner.
- Also exposed: tray menu "Pause", and the CLI `aileron --panic` (sends a signal to a running instance).
- Tested in `tests/safety/` and in the manual pre-release checklist on real hardware.

## 4. Watchdog design
- The control loop writes a heartbeat timestamp every tick.
- A separate thread checks it every 50 ms; if stale > 250 ms it calls `release_all()` and sets FAULT.
- A second guard monitors the capture thread; if no frames for 500 ms → treat as hand lost.
- Python GIL caveat: the watchdog and kill-switch use short, non-blocking operations; backend `release_all()` must be callable from any thread.

## 5. Held-input ledger
Every `ButtonDown`, `Key(down)`, `Pad(down)` and non-zero axis/trigger is recorded. `release_all()` drains the
ledger and verifies the backend reports an empty `held()` set; if not, it retries once, then logs an
error and shows a persistent warning. In tests the `NullBackend` asserts the ledger is empty at the end of
every scenario.

## 6. Privacy and data protection

| Data | Stored? | Where | Notes |
|------|---------|-------|-------|
| Camera frames | No | — | Processed in memory and discarded |
| Landmarks | Only on explicit recording / black box | Local files | No pixels, no identity data; user-deletable |
| Config / profiles | Yes | User config dir | Calibration values (body proportions) are mildly personal; stored locally only |
| Logs | Yes (rotating) | Local | No landmarks or images; no PII |
| Telemetry | No (opt-in only, if ever) | — | Not planned for v1 |

- Camera access is requested explicitly; the HUD/tray always shows camera state.
- When Aileron is not armed and no preview is open, an optional **low-power idle** mode releases the camera.
- The MediaPipe model runs on-device; no cloud inference.

## 7. Reliability targets
- No stuck input in 100% of the safety test scenarios (`TEST-03`).
- Crash-free session rate ≥ 99%.
- Recovery from camera disconnect without restart.
- Worst-case time from hand lost to released inputs: `hand_lost_ms` + one control tick (≈ 160 ms).

## 8. Pre-release manual safety checklist
- [ ] Kill switch works with the game/app in the foreground and with CPU load at 100%.
- [ ] Unplug camera mid-drag and mid-throttle → everything released.
- [ ] Kill the process (`taskkill`/`kill -9`) mid-drag → virtual gamepad disappears or is neutral; no stuck mouse button.
- [ ] Switch modes while throttle held → blocked or neutralized.
- [ ] Cover the camera with a hand → neutral within spec.
- [ ] Two people in frame → primary hand stays locked.
- [ ] Sleep/wake and monitor-change events → no stray input, mapping refreshed.

## 9. Incident handling
Any report of stuck input or unintended action is **severity 1**: reproduce with the black-box recording, add a
failing safety test (`TEST-07`), fix, and note it in `CHANGELOG.md`.
