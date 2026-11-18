# Roadmap — Aileron

Each milestone has an **exit criterion**: the milestone is done only when it is demonstrably met.

| # | Milestone | Deliverables | Exit criteria | Status |
|---|-----------|--------------|---------------|--------|
| **M0** | **Runway** (skeleton) | Repo, CI, `Lm` constants, capture thread, MediaPipe tracker, skeleton overlay, `NullBackend`, JSONL recorder/replayer, benchmark harness, `docs/benchmarks.md` | Live overlay at ≥ 30 fps; record → replay produces identical landmarks; CI green | Completed (commit 0581627) |
| **M1** | **Taxi** (cursor) | Features (palm size, anchor), One Euro filters, active-region mapping, multi-monitor/DPI, Windows mouse backend, `--panic`, kill switch | Cursor control usable; p95 latency ≤ 60 ms; kill switch works under load | Completed (commit f498237) |
| **M2** | **Takeoff** (clicks) | Pinch FSMs: click, drag, double, right, middle; click freeze; hysteresis; rate limits | Replay suite passes; ≤ 1 accidental click / 10 min in internal test | Completed (commit 4b8d014) |
| **M3** | **Climb** (scroll, zoom, clutch) | V-sign scroll, two-hand zoom, fist/palm clutch, arm/disarm, state machine, HUD basics | All Pointer FRs (M-priority) done; clutch verified | Completed (commit 146f179) |
| **M4** | **Pressurize** (safety layer) | Safety gate, watchdog, held-input ledger, fault handling, full safety suite, manual checklist | 100% safety tests pass; checklist signed off on Windows | Completed (commit 2113d47) |
| **M5** | **Cruise** (Cockpit: Yoke) | Gamepad backend (Windows), steering/throttle/brake, pre-flight calibration, ramp-in, neutral hold, gamepad test page | Reference lap within 140% of gamepad baseline (initial), latency ≤ 50 ms | Completed (commit 205db57) |
| **M6** | **Handlebar and polish** | Handlebar profile, buttons/gears, profiles import/export, tray, HUD complete, accessibility options, keyboard PWM fallback | All M and S requirements implemented | Completed (commit 0d98eb5) |
| **M7** | **Hardening** | Performance tuning, Linux backend, macOS Pointer, plugin entry points, low-power idle, packaging/installer | Success metrics in `PRD.md` §8 met or gaps documented | Completed (v0.1.0-rc1) |
| **v1.0** | **Cleared for takeoff** | Release candidate, docs final, known-issues list | `PRD.md` §11 satisfied | Tagged: `v0.1.0-rc1` |
| **v1.x** | Stick (flight) profile, custom gesture editor, per-app profiles, plugin docs, speed-sensitive steering via telemetry, GPU delegate tuning | | Planned post-v1.0 |

## Suggested timeline (single developer, part-time estimates)
M0 1–2 wks · M1 2 wks · M2 2 wks · M3 2 wks · M4 1–2 wks · M5 3 wks · M6 3 wks · M7 3–4 wks.
Shorten by cutting S/C items; never cut M4.

## Early spikes (do first, in parallel with M0)
1. **Latency spike:** camera → MediaPipe → print timestamp; measure real numbers on target hardware.
2. **Gamepad driver spike:** confirm a virtual gamepad works with one target game and decide on the backend (`PRD R4`).
3. **Throttle spike:** quick prototype of index-extension vs. thumb vs. wrist-twist signals; look at noise on recorded data.
4. **Hand-size/lighting spike:** record 5 users in varied lighting to size the confidence thresholds.

## Definition of Ready for a task
Spec row in the relevant doc, config keys named, test plan stated, rules affected listed.
