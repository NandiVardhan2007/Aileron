# KNOWN_ISSUES.md — Aileron

> Tracks known limitations, hardware verification gaps, and platform-specific caveats.
> Updated throughout autonomous development.

## 1. Hardware Verification Gaps (Unverified on Physical Hardware)
All items below have been validated using synthetic landmark feeds, replay tests, or software mocks. Physical verification requires dedicated user testing with real hardware.

- [ ] **Real OS Mouse Injection (Windows SendInput):** Verified via unit tests and mocks; live injection disarmed during development per Safety Contract.
- [ ] **Windows Global Hotkey (RegisterHotKey):** Threaded hotkey loop verified via unit test mocks; requires physical keyboard press test on desktop.
- [ ] **Virtual Gamepad Driver (ViGEmBus / vgamepad):** Verified via `NullBackend` and mock `vgamepad.VX360Gamepad`; physical Xbox 360 controller emulation and game ingestion unverified.
- [ ] **Linux evdev/uinput & macOS Quartz backends:** Verified via mock tests; physical execution on Linux kernel and macOS Quartz requires platform-specific hardware and permissions.
- [ ] **PyInstaller Binary Deployment:** Tested spec and assets via dry-run build; packaged single-file/folder distribution requires code signing and smoke testing on clean target machines.
- [ ] **Real Lighting, Skin Tone & Occlusion Variations:** MediaPipe tracking stability under harsh backlight or varied skin pigmentation requires empirical human user study.
- [ ] **Glass-to-Glass Latency:** Software pipeline latency (capture timestamp to output dispatch) is instrumented; physical photon-to-display latency requires high-speed optical test rig.

## 2. Platform & Ecosystem Caveats
- **ViGEmBus Maintenance Status:** ViGEmBus has been reported as unmaintained upstream (ADR-005). The `vgamepad` Python library relies on it on Windows. `KeyboardPwmGamepad` is provided as universal fallback.
- **Single-Camera Depth Estimation:** MediaPipe `world_landmarks` provides metric approximation, but Z-axis depth variance is higher than X/Y in-plane movement.
