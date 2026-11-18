# Benchmarks & Latency Reference — Aileron

> Reference machine specification, measurement methodology, performance budgets, and empirical benchmark logs.

## 1. Reference Machine Specifications
- **Operating System:** Windows 11 (64-bit)
- **Runtime:** Python 3.12 (CPython), uv package runner
- **Reference Camera:** 720p @ 60 FPS (USB 3.0 / Integrated webcam)
- **Computer Vision:** MediaPipe Tasks `HandLandmarker` (LIVE_STREAM async mode)
- **Math / Numeric:** NumPy 2.x

## 2. Performance Budgets (PERF §5)

| Metric | Budget Target | Safety / UX Rationale |
|---|---|---|
| Glass-to-output latency, Pointer mode (p95) | ≤ 60 ms | Prevent hand-eye lag in cursor tracking |
| Glass-to-output latency, Cockpit mode (p95) | ≤ 50 ms | High-speed vehicle simulation responsiveness |
| Inference + processing per frame (p95) | ≤ 12 ms | Sustained 60+ FPS processing without dropping frames |
| Control loop tick jitter (p95) | ≤ 2 ms | Deterministic filter stepping and dwell timing |
| CPU use, steady state | ≤ 25% of 1 core | Avoid competing with games or host applications |
| Hand-lost neutralization | ≤ 150 ms (+1 tick) | Immediate fail-safe release on camera departure |
| Kill switch response | ≤ 1 control tick (~8 ms) | Immediate user-override guarantee |

## 3. Milestone Benchmark Log

| Milestone | Date | Scenario | Samples | p50 Latency (ms) | p95 Latency (ms) | Max Latency (ms) | Status |
|---|---|---|---|---|---|---|---|
| **M0 Baseline** | 2026-11-18 | Replay pipeline (NullBackend) | 1,000 | 0.85 ms (pipeline only) | 1.80 ms (pipeline only) | 4.20 ms | GREEN |
| **M0 Synthetic** | 2026-11-18 | Full simulated glass-to-emit | 500 | 35.12 ms | 52.84 ms | 58.40 ms | GREEN (≤ 60 ms) |
| **M1 Taxi** | 2026-11-18 | Feature extraction + cursor filter + SendInput mock | 500 | 33.48 ms | 44.48 ms | 61.31 ms | GREEN (≤ 60 ms) |
| **M2 Takeoff** | 2026-11-18 | Pipeline: features + pinch FSMs + cursor map + gate | 480 | 0.11 ms (pipe) / 33.6 ms (total) | 0.20 ms (pipe) / 44.6 ms (total) | 0.66 ms (pipe) | GREEN (≤ 60 ms) |
| **M3 Climb** | 2026-11-18 | Pipeline: full gestures (pinch, scroll, zoom, dwell) + session/mode managers | 500 | 0.14 ms (pipe) / 33.7 ms (total) | 0.27 ms (pipe) / 44.7 ms (total) | 0.81 ms (pipe) | GREEN (≤ 60 ms) |

*Note: In automated replay and unit test runs without physical sensor capture, the pipeline-only software processing latency (feature extraction + filters + gestures + mapping + NullBackend) is measured. Physical optical latency is documented in HUMAN_TODO.md.*
