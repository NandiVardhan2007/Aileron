# Changelog
All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com), versioning: SemVer.
Changing a default threshold counts as a behavior change and must be listed.

## [Unreleased]
### Added
- **M1 Taxi:**
  - Scale-invariant feature extraction (`palm_size`, `anchor`, finger `curl`, `pinch` ratios, `roll_deg`, `palm_normal`).
  - 1D and 2D One Euro adaptive low-pass filter implementations (`SIG-05`).
  - Active-region cursor mapping supporting absolute (virtual desktop) and relative modes with gamma gain and click freeze damping.
  - Fail-safe `HeldInputLedger` and `SafetyGate` enforcing state gating, rate limits, and desktop clamping.
  - Windows mouse and keyboard backend (`WindowsMouseKeyboardBackend`) using native Win32 `SendInput` behind lazy import.
  - OS-level global kill switch (`KillSwitchListener`) registering `Ctrl+Alt+Esc` on dedicated thread (`SAFE-01`).
  - Filter tuning analysis tool `tools/tune_filters.py`.
- **M0 Runway:**
  - MediaPipe 21-point hand landmark named constants (`Lm`) and finger chains.
  - Core data contracts: `Frame`, `Hand`, `HandFrame`, `HandFeatures`, `Signals`, `Intent` hierarchy.
  - Pydantic v2 configuration schema and hierarchical TOML defaults loader.
  - Capture thread with single-slot latest-frame queue and horizontal mirroring.
  - MediaPipe Tasks `HandLandmarker` async tracker wrapper.
  - Safe `NullBackend` with held-input ledger and intent recording.
  - OpenCV skeleton overlay and HUD status renderer.
  - JSONL landmark recorder and replayer (`PRIV-02`).
  - Synthetic landmark generator `tools/synth_landmarks.py` and 15 standard test fixtures.
  - Latency benchmarking harness `tools/plot_latency.py` and `docs/benchmarks.md`.
  - GitHub Actions CI workflow for lint, format, type-checking, and pytest.
- Project documentation set, architecture and safety design.
