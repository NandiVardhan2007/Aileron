"""Latency and throughput benchmark analysis tool for Aileron."""

import argparse
import statistics
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class LatencyReport:
    """Latency benchmark statistics."""

    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    mean_ms: float
    stdev_ms: float
    fps: float


def compute_percentiles(values: list[float]) -> dict[str, float]:
    """Compute p50, p95, p99 from sorted values in milliseconds."""
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0, "stdev": 0.0}
    s = sorted(values)
    n = len(s)
    p50 = s[int(0.50 * n)]
    p95 = s[min(int(0.95 * n), n - 1)]
    p99 = s[min(int(0.99 * n), n - 1)]
    mean = statistics.mean(s)
    stdev = statistics.stdev(s) if n > 1 else 0.0
    return {
        "p50": p50,
        "p95": p95,
        "p99": p99,
        "max": s[-1],
        "mean": mean,
        "stdev": stdev,
    }


def analyze_latencies(latencies_ns: list[int], total_duration_s: float) -> LatencyReport:
    """Convert raw nanosecond latencies to ms statistics and throughput."""
    lat_ms = [x / 1_000_000.0 for x in latencies_ns]
    pct = compute_percentiles(lat_ms)
    fps = len(latencies_ns) / total_duration_s if total_duration_s > 0 else 0.0
    return LatencyReport(
        count=len(latencies_ns),
        p50_ms=pct["p50"],
        p95_ms=pct["p95"],
        p99_ms=pct["p99"],
        max_ms=pct["max"],
        mean_ms=pct["mean"],
        stdev_ms=pct["stdev"],
        fps=fps,
    )


def format_benchmark_table(report: LatencyReport, label: str = "Pipeline Benchmark") -> str:
    """Format benchmark report into a human-readable table."""
    status_p95 = "PASS (<=60ms)" if report.p95_ms <= 60.0 else "BUDGET MISS (>60ms)"
    lines = [
        f"=== {label} ===",
        f"Sample count:   {report.count}",
        f"Throughput:     {report.fps:.1f} FPS",
        f"p50 Latency:    {report.p50_ms:.2f} ms",
        f"p95 Latency:    {report.p95_ms:.2f} ms  [{status_p95}]",
        f"p99 Latency:    {report.p99_ms:.2f} ms",
        f"Max Latency:    {report.max_ms:.2f} ms",
        f"Mean +/- Stdev: {report.mean_ms:.2f} +/- {report.stdev_ms:.2f} ms",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aileron Latency Benchmarking Tool")
    parser.add_argument(
        "--synthetic", action="store_true", help="Run a synthetic latency simulation benchmark"
    )
    parser.add_argument("--samples", type=int, default=500, help="Number of benchmark samples")

    args = parser.parse_args()

    if args.synthetic:
        # Simulate realistic software pipeline delays
        import random

        simulated_latencies = []
        t_start = time.monotonic()
        for _ in range(args.samples):
            lat_ns = int((30.0 + random.expovariate(0.2)) * 1_000_000)
            simulated_latencies.append(lat_ns)
        t_dur = time.monotonic() - t_start

        rep = analyze_latencies(simulated_latencies, max(0.01, t_dur))
        print(format_benchmark_table(rep, "Synthetic Latency Benchmark"))
    else:
        # Benchmark real software pipeline processing time on replay fixtures
        from pathlib import Path

        from aileron.config import load_config
        from aileron.features.extraction import extract_features
        from aileron.gestures.engine import GestureEngine
        from aileron.interfaces import SessionState
        from aileron.output.null import NullBackend
        from aileron.replay import ReplayReader
        from aileron.safety.gate import SafetyGate

        config = load_config()
        engine = GestureEngine(config)
        gate = SafetyGate(initial_state=SessionState.ARMED)
        backend = NullBackend()
        backend.open()

        fixture_path = Path("tests/replay/pinch_click.jsonl")
        if not fixture_path.is_file():
            fixture_path = Path("tests/replay/move_fast.jsonl")

        reader = ReplayReader(fixture_path)
        frames, _ = reader.load_all()

        latencies_ns: list[int] = []
        t_start = time.monotonic()

        for _ in range(max(1, args.samples // max(1, len(frames)))):
            for frame in frames:
                t0 = time.perf_counter_ns()
                feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
                output, intents = engine.process(frame, feats)
                filtered = gate.filter(intents, now_ns=frame.t_capture_ns)
                backend.apply(filtered)
                t1 = time.perf_counter_ns()
                latencies_ns.append(t1 - t0)

        t_dur = time.monotonic() - t_start
        backend.close()

        rep = analyze_latencies(latencies_ns, max(0.001, t_dur))
        print(format_benchmark_table(rep, "Active Software Pipeline Benchmark (M2)"))
