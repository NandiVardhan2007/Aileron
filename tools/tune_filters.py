"""Tool for tuning One Euro filter cutoff and beta coefficients against recorded signals."""

import argparse
import math
from pathlib import Path

from aileron.filters.one_euro import OneEuroFilter1D
from aileron.replay import ReplayReader


def evaluate_filter_on_signal(
    timestamps_ns: list[int],
    values: list[float],
    min_cutoff: float,
    beta: float,
    d_cutoff: float = 1.0,
) -> tuple[float, float]:
    """Calculate RMS jitter and lag for a given set of filter parameters."""
    f = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
    filtered = []
    for t_ns, val in zip(timestamps_ns, values, strict=True):
        filtered.append(f(val, t_ns))

    # Jitter: standard deviation of second-difference (roughness)
    diffs2 = []
    for i in range(2, len(filtered)):
        d2 = filtered[i] - 2 * filtered[i - 1] + filtered[i - 2]
        diffs2.append(d2)

    rms_jitter = math.sqrt(sum(d * d for d in diffs2) / max(1, len(diffs2))) if diffs2 else 0.0

    # Lag: mean squared error against original during dynamic phases
    mse = sum((orig - filt) ** 2 for orig, filt in zip(values, filtered, strict=True)) / max(
        1, len(values)
    )
    rms_lag = math.sqrt(mse)

    return rms_jitter, rms_lag


def tune_replay_file(replay_path: Path) -> None:
    """Run grid search over min_cutoff and beta on anchor coordinates from a replay file."""
    reader = ReplayReader(replay_path)
    frames, _ = reader.load_all()

    timestamps = []
    xs = []
    for fr in frames:
        if fr.hands:
            timestamps.append(fr.t_capture_ns)
            xs.append(float(fr.hands[0].lm[5, 0]))  # index MCP x

    if len(xs) < 10:
        print(f"Replay {replay_path} contains too few frames for tuning.")
        return

    print(f"Tuning filters on '{replay_path.name}' ({len(xs)} samples):")
    print(f"{'min_cutoff (Hz)':<16}{'beta':<10}{'RMS Jitter':<16}{'RMS Lag':<16}")
    print("-" * 58)

    for min_c in [0.8, 1.2, 1.6, 2.5]:
        for b in [1.0, 4.0, 8.0, 15.0]:
            jitter, lag = evaluate_filter_on_signal(timestamps, xs, min_cutoff=min_c, beta=b)
            print(f"{min_c:<16.2f}{b:<10.1f}{jitter:<16.6f}{lag:<16.6f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tune One Euro filter parameters on recorded replays"
    )
    parser.add_argument(
        "--replay", type=str, default="tests/replay/move_slow.jsonl", help="Replay file to evaluate"
    )
    args = parser.parse_args()
    tune_replay_file(Path(args.replay))
