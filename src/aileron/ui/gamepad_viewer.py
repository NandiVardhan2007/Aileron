"""Gamepad axis and trigger testing viewer for CLI and HUD (M5).

Follows COCKPIT_MODE §6.1 and ROADMAP M5:
- Visual/textual status of steering axis (LX), throttle (RT), brake (LT), and buttons.
- Runs standalone via --gamepad-test or integrates into OpenCV overlay.
"""

from __future__ import annotations

import time

from aileron.modes.yoke import YokeTelemetry


def format_gamepad_ascii_bar(val: float, width: int = 20, bipolar: bool = False) -> str:
    """Render an ASCII progress bar for unipolar (0..1) or bipolar (-1..1) axes."""
    if bipolar:
        # Range -1.0 to 1.0, center is 0.0
        center = width // 2
        clamped = max(-1.0, min(1.0, val))
        pos = int(center + (clamped * center))
        bar = ["-"] * width
        bar[center] = "|"
        bar[min(max(pos, 0), width - 1)] = "O"
        return f"[{''.join(bar)}] {val:+.2f}"

    # Unipolar 0.0 to 1.0
    clamped = max(0.0, min(1.0, val))
    filled = int(clamped * width)
    bar_str = "=" * filled + " " * (width - filled)
    return f"[{bar_str}] {val:.2f}"


def render_gamepad_test_text(telemetry: YokeTelemetry) -> str:
    """Format full multi-line text view of gamepad controller state."""
    steer_bar = format_gamepad_ascii_bar(telemetry.steer_axis, width=20, bipolar=True)
    throttle_bar = format_gamepad_ascii_bar(telemetry.throttle, width=20, bipolar=False)
    brake_bar = format_gamepad_ascii_bar(telemetry.brake, width=20, bipolar=False)
    pct = int(telemetry.neutral_hold_progress * 100)
    status = "LIVE" if telemetry.is_live else f"HOLD ({pct}%)"

    return (
        f"AILERON GAMEPAD TEST -- Status: {status}\n"
        f"  Steering (LX): {steer_bar} (angle: {telemetry.steer_deg:+.1f} deg)\n"
        f"  Throttle (RT): {throttle_bar}\n"
        f"  Brake    (LT): {brake_bar}\n"
    )


def run_gamepad_test(max_ticks: int | None = None) -> None:
    """Run interactive terminal axis tester."""
    print("=" * 60)
    print("Aileron Gamepad Axis Tester (--gamepad-test)")
    print("Press Ctrl+C to exit.")
    print("=" * 60)

    # Simulated demo telemetry
    ticks = 0
    telem = YokeTelemetry(is_live=True)

    try:
        while True:
            if max_ticks and ticks >= max_ticks:
                break
            ticks += 1
            # Render snapshot
            text = render_gamepad_test_text(telem)
            print(f"\r{text}", end="")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nGamepad test stopped.")
