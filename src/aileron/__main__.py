"""CLI entry point and runtime launcher for Aileron."""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import sys
import time
from pathlib import Path

import cv2

from aileron.capture import CaptureThread
from aileron.config import AileronConfig, load_config
from aileron.control import ControlPipeline, StepResult
from aileron.interfaces import Frame, HandFrame, SessionState
from aileron.output.base import OutputBackend
from aileron.output.null import NullBackend
from aileron.replay import ReplayReader
from aileron.ui.gamepad_viewer import run_gamepad_test
from aileron.ui.overlay import draw_hud
from aileron.vision.tracker import HandTracker, ensure_model_file

logger = logging.getLogger("aileron")


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


def _create_backend(choice: str) -> OutputBackend:
    """Resolve requested backend safely according to host platform."""
    backend: OutputBackend = NullBackend()

    if choice in ("mouse", "windows", "auto") and sys.platform == "win32":
        from aileron.output.windows import WindowsMouseKeyboardBackend  # noqa: PLC0415

        backend = WindowsMouseKeyboardBackend()
    elif choice == "gamepad":
        from aileron.output.gamepad import KeyboardPwmGamepad, VGamepadBackend  # noqa: PLC0415

        try:
            backend = VGamepadBackend()
        except Exception:
            backend = KeyboardPwmGamepad()

    return backend


def _init_vision(config: AileronConfig) -> tuple[CaptureThread, HandTracker | None]:
    """Initialize camera capture thread and MediaPipe tracker."""
    capture = CaptureThread(config=config.camera)
    capture.start()

    time.sleep(0.1)
    if capture.latest_error is not None:
        raise RuntimeError(f"Camera failed to start: {capture.latest_error}")

    tracker: HandTracker | None = None
    try:
        model_path = ensure_model_file()
        tracker = HandTracker(
            config=config.tracking,
            model_path=model_path,
            is_mirrored=config.camera.mirror,
        )
    except Exception as exc:
        print(f"[WARN] Could not initialize HandTracker ({exc}). Running headless.")

    return capture, tracker


def _render_hud(
    show_hud: bool,
    frame: Frame | None,
    hand_frame: HandFrame | None,
    pipeline: ControlPipeline | None = None,
    step_result: StepResult | None = None,
    fps: float | None = None,
) -> bool:
    """Render skeleton and status overlay; returns True if user pressed quit key."""
    if not show_hud or frame is None or frame.image is None:
        return False

    session_state = SessionState.DISARMED
    mode_str = "POINTER"
    dwell_progress = None
    cursor_anchor = None
    is_frozen = False

    if pipeline is not None:
        session_state = pipeline.session_manager.state
        mode_str = pipeline.mode_manager.mode.name
        is_frozen = getattr(pipeline.engine.mapper, "_click_freeze", False)

    if step_result is not None and step_result.output is not None:
        dwell_progress = step_result.output.signals.dwell_progress
        cursor_anchor = step_result.output.signals.cursor

    canvas = draw_hud(
        frame.image,
        session_state=session_state,
        mode_str=mode_str,
        hand_frame=hand_frame,
        fps=fps,
        dwell_progress=dwell_progress,
        cursor_anchor=cursor_anchor,
        is_frozen=is_frozen,
    )
    cv2.imshow("Aileron", canvas)
    key = cv2.waitKey(1) & 0xFF
    return key in (27, ord("q"))


def run_live(
    config: AileronConfig,
    backend_choice: str = "null",
    show_hud: bool = True,
    debug: bool = False,
    max_frames: int | None = None,
) -> None:
    """Run live camera capture and control pipeline."""
    backend = _create_backend(backend_choice)
    try:
        backend.open()
    except Exception as e:
        print(f"[WARN] Backend '{backend_choice}' unavailable ({e}). Falling back to NullBackend.")
        backend = NullBackend()
        backend.open()

    print(
        f"Aileron initialized. State: DISARMED. Backend: {backend.name}. Safety invariant: SAFE-05."
    )
    print("Hold open palm in front of camera for 0.4s to arm. Press Ctrl+Alt+Esc or 'q' to exit.")

    try:
        capture, tracker = _init_vision(config)
    except Exception as err:
        print(f"[ERROR] {err}\nEnsure webcam is connected. Use --replay for offline tests.")
        backend.close()
        return

    pipeline = ControlPipeline(
        config=config,
        backend=backend,
        capture_thread=capture,
        start_watchdog=True,
    )

    frame_count = 0
    try:
        while True:
            if max_frames is not None and frame_count >= max_frames:
                break

            frame = capture.get_latest_frame(timeout_s=0.05)
            hand_frame = None

            if frame is not None and tracker is not None:
                tracker.process_frame(frame)
                hand_frame = tracker.get_latest_hand_frame(timeout_s=0.01)

            step_result = pipeline.step(hand_frame)
            frame_count += 1

            if _render_hud(
                show_hud,
                frame,
                hand_frame,
                pipeline=pipeline,
                step_result=step_result,
            ):
                break

            if Path(".aileron_panic").exists():
                print("[PANIC] Panic flag detected; neutralizing and shutting down.")
                Path(".aileron_panic").unlink(missing_ok=True)
                break
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    finally:
        pipeline.shutdown()
        if tracker is not None:
            tracker.close()
        capture.stop()
        backend.close()
        if show_hud:
            with contextlib.suppress(Exception):
                cv2.destroyAllWindows()
        print(f"Aileron stopped cleanly. Total ticks: {frame_count}.")


def main() -> None:
    """Parse CLI arguments and launch Aileron."""
    parser = argparse.ArgumentParser(
        prog="aileron",
        description="Aileron: Touchless air-mouse and simulator controller driven by MediaPipe",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Arm live input backend (sets backend to auto/mouse instead of null)",
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

    if args.gamepad_test:
        run_gamepad_test(max_ticks=args.headless_frames)
        sys.exit(0)

    if args.replay:
        run_replay(args.replay, debug=args.debug, max_frames=args.headless_frames)
        sys.exit(0)

    # Launch live control loop
    show_hud = not args.no_hud and args.headless_frames is None
    backend_choice = "auto" if args.live else args.backend
    run_live(
        config=cfg,
        backend_choice=backend_choice,
        show_hud=show_hud,
        debug=args.debug,
        max_frames=args.headless_frames,
    )


if __name__ == "__main__":
    main()
