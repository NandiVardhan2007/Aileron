# Changelog
All notable changes are documented here. Format: [Keep a Changelog](https://keepachangelog.com), versioning: SemVer.
Changing a default threshold counts as a behavior change and must be listed.

## [Unreleased]
### Added
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
