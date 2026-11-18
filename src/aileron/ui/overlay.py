"""OpenCV-based skeleton overlay and HUD status renderer."""

import cv2
import numpy as np

from aileron.interfaces import Hand, HandFrame, SessionState
from aileron.landmarks import HAND_CONNECTIONS, Lm

# Colors in BGR
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_GREEN = (50, 205, 50)
COLOR_AMBER = (0, 165, 255)
COLOR_RED = (50, 50, 230)
COLOR_CYAN = (230, 216, 0)
COLOR_GREY = (128, 128, 128)
COLOR_BLUE = (255, 120, 0)
COLOR_BG_BOX = (30, 30, 30)

SCORE_CONFIDENT_THRESHOLD = 0.6
POINT_RADIUS = 4
LINE_THICKNESS = 2

STATE_COLORS: dict[SessionState, tuple[int, int, int]] = {
    SessionState.BOOT: COLOR_GREY,
    SessionState.DISARMED: COLOR_AMBER,
    SessionState.ARMED: COLOR_GREEN,
    SessionState.STANDBY: COLOR_BLUE,
    SessionState.FAULT: COLOR_RED,
}


def draw_skeleton(
    canvas: np.ndarray,
    hand: Hand,
    color: tuple[int, int, int] = COLOR_GREEN,
    point_radius: int = POINT_RADIUS,
    line_thickness: int = LINE_THICKNESS,
) -> None:
    """Draw 21 hand landmarks and skeleton bones on a BGR image."""
    h, w = canvas.shape[:2]
    pts_px: dict[int, tuple[int, int]] = {}

    for i in range(21):
        x = int(np.clip(hand.lm[i, 0] * w, 0, w - 1))
        y = int(np.clip(hand.lm[i, 1] * h, 0, h - 1))
        pts_px[i] = (x, y)

    # Draw bones
    for start_lm, end_lm in HAND_CONNECTIONS:
        if int(start_lm) in pts_px and int(end_lm) in pts_px:
            cv2.line(
                canvas,
                pts_px[int(start_lm)],
                pts_px[int(end_lm)],
                color,
                line_thickness,
                cv2.LINE_AA,
            )

    # Draw landmark points
    for i, pt in pts_px.items():
        # Highlight fingertips
        if i in (
            Lm.THUMB_TIP,
            Lm.INDEX_FINGER_TIP,
            Lm.MIDDLE_FINGER_TIP,
            Lm.RING_FINGER_TIP,
            Lm.PINKY_TIP,
        ):
            cv2.circle(canvas, pt, point_radius + 2, COLOR_CYAN, -1, cv2.LINE_AA)
        else:
            cv2.circle(canvas, pt, point_radius, color, -1, cv2.LINE_AA)

    # Label handedness and score near wrist
    wrist_pt = pts_px[int(Lm.WRIST)]
    label = f"{hand.side.value.upper()} ({hand.score:.2f})"
    cv2.putText(
        canvas,
        label,
        (wrist_pt[0] - 20, wrist_pt[1] + 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        COLOR_WHITE,
        1,
        cv2.LINE_AA,
    )


def draw_hud(
    canvas: np.ndarray,
    session_state: SessionState = SessionState.DISARMED,
    mode_str: str = "POINTER",
    hand_frame: HandFrame | None = None,
    fps: float | None = None,
    latency_ms: float | None = None,
    dwell_progress: dict[str, float] | None = None,
    cursor_anchor: tuple[float, float] | None = None,
    is_frozen: bool = False,
) -> np.ndarray:
    """Render HUD chips, state banners, skeleton overlay, telemetry, dwell, and cursor halo."""
    out = canvas.copy()
    h, w = out.shape[:2]

    # Draw hands if present
    if hand_frame and hand_frame.hands:
        for hand in hand_frame.hands:
            skel_color = COLOR_GREEN if hand.score >= SCORE_CONFIDENT_THRESHOLD else COLOR_AMBER
            draw_skeleton(out, hand, color=skel_color)
    else:
        # Prompt if no hands visible
        cv2.putText(
            out,
            "Searching for hand...",
            (w // 2 - 100, h - 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            COLOR_GREY,
            1,
            cv2.LINE_AA,
        )

    # Draw Cursor Halo and Reticle
    if cursor_anchor is not None:
        cx = int(np.clip(cursor_anchor[0] * w, 0, w - 1))
        cy = int(np.clip(cursor_anchor[1] * h, 0, h - 1))
        halo_radius = 12 if is_frozen else 18
        halo_color = COLOR_AMBER if is_frozen else COLOR_CYAN
        cv2.circle(out, (cx, cy), halo_radius, halo_color, 2, cv2.LINE_AA)
        cv2.circle(out, (cx, cy), 3, COLOR_WHITE, -1, cv2.LINE_AA)

    # Top-left HUD badge: Session State Chip
    state_color = STATE_COLORS.get(session_state, COLOR_GREY)
    state_text = session_state.name
    cv2.rectangle(out, (15, 15), (145, 48), COLOR_BG_BOX, -1)
    cv2.rectangle(out, (15, 15), (145, 48), state_color, 2)
    cv2.putText(
        out,
        state_text,
        (25, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        state_color,
        2,
        cv2.LINE_AA,
    )

    # Mode Badge
    cv2.rectangle(out, (155, 15), (285, 48), COLOR_BG_BOX, -1)
    cv2.putText(
        out,
        mode_str,
        (165, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        COLOR_WHITE,
        1,
        cv2.LINE_AA,
    )

    # Dwell Progress Arc / Indicators
    if dwell_progress:
        y_dwell = 75
        for name, prog in dwell_progress.items():
            if prog > 0.0:
                bar_w = 120
                filled_w = int(bar_w * np.clip(prog, 0.0, 1.0))
                cv2.rectangle(out, (15, y_dwell), (15 + bar_w, y_dwell + 14), COLOR_BG_BOX, -1)
                cv2.rectangle(out, (15, y_dwell), (15 + filled_w, y_dwell + 14), COLOR_CYAN, -1)
                cv2.rectangle(out, (15, y_dwell), (15 + bar_w, y_dwell + 14), COLOR_WHITE, 1)
                cv2.putText(
                    out,
                    f"{name.upper()} {int(prog * 100)}%",
                    (15 + bar_w + 10, y_dwell + 11),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    COLOR_WHITE,
                    1,
                    cv2.LINE_AA,
                )
                y_dwell += 22

    # Telemetry metrics (Top Right)
    telem_parts = []
    if fps is not None:
        telem_parts.append(f"{fps:.1f} FPS")
    if latency_ms is not None:
        telem_parts.append(f"{latency_ms:.1f} ms")
    if telem_parts:
        telem_str = " | ".join(telem_parts)
        cv2.putText(
            out,
            telem_str,
            (w - 180, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            COLOR_WHITE,
            1,
            cv2.LINE_AA,
        )

    return out
