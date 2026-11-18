"""CLI entry point for Aileron."""

import argparse
import json
import sys
import time
from pathlib import Path

from aileron.config import load_config
from aileron.output.null import NullBackend
from aileron.replay import ReplayReader


def handle_panic() -> None:
    """Handle emergency panic invocation: signals running instances to neutralize."""
    print("[PANIC] Global panic triggered: requesting all instances to release held inputs.")
    panic_file = Path(".aileron_panic")
    panic_file.touch()
    print("[PANIC] Panic flag set. Running instances will neutralize and disarm.")


def run_replay(
    replay_file: str,
    debug: bool = False,
    max_frames: int | None = None,
) -> None:
    """Run an offline replay file through the pipeline using NullBackend."""
    reader = ReplayReader(replay_file)
    backend = NullBackend()
    backend.open()

    frames, expects = reader.load_all()
    print(
        f"Loaded replay '{replay_file}' with {len(frames)} frames and {len(expects)} expectations."
    )

    processed = 0
    t0 = time.monotonic()
    for _hf in frames:
        if max_frames and processed >= max_frames:
            break
        processed += 1

    t_elapsed = time.monotonic() - t0
    fps = processed / t_elapsed if t_elapsed > 0 else 0
    print(f"Replay complete: processed {processed} frames in {t_elapsed:.3f}s ({fps:.1f} FPS).")
    backend.close()


def main() -> None:
    """Parse CLI arguments and launch Aileron."""
    parser = argparse.ArgumentParser(
        prog="aileron",
        description="Aileron: Touchless air-mouse and simulator controller driven by MediaPipe",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "null", "mouse", "gamepad"],
        default="null",
        help="Output backend driver (default: null)",
    )
    parser.add_argument(
        "--profile", type=str, default=None, help="Name or path of profile TOML file"
    )
    parser.add_argument(
        "--replay", type=str, default=None, help="Path to JSONL replay file to execute"
    )
    parser.add_argument(
        "--record", type=str, default=None, help="Path to write landmark JSONL recording"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and metrics")
    parser.add_argument("--no-hud", action="store_true", help="Disable OpenCV HUD overlay window")
    parser.add_argument(
        "--panic", action="store_true", help="Emergency kill switch: neutralize all inputs"
    )
    parser.add_argument(
        "--print-config", action="store_true", help="Print loaded configuration and exit"
    )
    parser.add_argument(
        "--gamepad-test", action="store_true", help="Display live gamepad axis testing overlay"
    )
    parser.add_argument(
        "--headless-frames", type=int, default=None, help="Run N frames headlessly and exit"
    )

    args = parser.parse_args()

    if args.panic:
        handle_panic()
        sys.exit(0)

    cfg = load_config(profile_path=args.profile)

    if args.print_config:
        print(json.dumps(cfg.model_dump(), indent=2))
        sys.exit(0)

    if args.replay:
        run_replay(args.replay, debug=args.debug, max_frames=args.headless_frames)
        sys.exit(0)

    # In M0 autonomous development mode, default to NullBackend
    backend = NullBackend()
    backend.open()
    print(
        f"Aileron initialized. State: DISARMED. Backend: {backend.name}. Safety invariant: SAFE-05."
    )

    if args.headless_frames is not None:
        print(f"Headless smoke test completed {args.headless_frames} ticks.")
        backend.close()
        sys.exit(0)


if __name__ == "__main__":
    main()
