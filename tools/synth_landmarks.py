"""Parametric 21-landmark hand pose and motion stream generator for Aileron replay fixtures."""

import argparse
import math
from pathlib import Path

import numpy as np

from aileron.interfaces import Hand, HandFrame, Side
from aileron.landmarks import Lm
from aileron.replay import ReplayWriter

# Canonical rest hand proportions in meters (hand-centered: wrist at 0,0,0)
# Palm size is roughly 0.10m to 0.12m in metric space
BASE_WORLD_LM: dict[int, tuple[float, float, float]] = {
    Lm.WRIST: (0.000, 0.000, 0.000),
    Lm.THUMB_CMC: (0.035, 0.025, -0.010),
    Lm.THUMB_MCP: (0.055, 0.055, -0.015),
    Lm.THUMB_IP: (0.070, 0.085, -0.018),
    Lm.THUMB_TIP: (0.080, 0.110, -0.020),
    Lm.INDEX_FINGER_MCP: (0.030, 0.100, 0.000),
    Lm.INDEX_FINGER_PIP: (0.035, 0.140, 0.005),
    Lm.INDEX_FINGER_DIP: (0.038, 0.170, 0.008),
    Lm.INDEX_FINGER_TIP: (0.040, 0.195, 0.010),
    Lm.MIDDLE_FINGER_MCP: (0.000, 0.105, 0.000),
    Lm.MIDDLE_FINGER_PIP: (0.000, 0.150, 0.005),
    Lm.MIDDLE_FINGER_DIP: (0.000, 0.185, 0.008),
    Lm.MIDDLE_FINGER_TIP: (0.000, 0.215, 0.010),
    Lm.RING_FINGER_MCP: (-0.028, 0.100, 0.000),
    Lm.RING_FINGER_PIP: (-0.032, 0.142, 0.005),
    Lm.RING_FINGER_DIP: (-0.035, 0.172, 0.008),
    Lm.RING_FINGER_TIP: (-0.038, 0.198, 0.010),
    Lm.PINKY_MCP: (-0.055, 0.085, 0.000),
    Lm.PINKY_PIP: (-0.065, 0.120, 0.005),
    Lm.PINKY_DIP: (-0.072, 0.145, 0.008),
    Lm.PINKY_TIP: (-0.078, 0.168, 0.010),
}


def _rotate_z(points: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotate (N, 3) points around Z axis."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    rot = np.array(
        [
            [cos_a, -sin_a, 0.0],
            [sin_a, cos_a, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )
    return points @ rot.T


def generate_hand_landmarks(
    pose: str = "open_palm",
    side: Side = Side.RIGHT,
    center_xy: tuple[float, float] = (0.5, 0.5),
    palm_scale: float = 0.15,
    roll_deg: float = 0.0,
    noise_sigma: float = 0.0,
    aspect: float = 16.0 / 9.0,
    extension_ramp: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate (21, 3) normalized image landmarks and (21, 3) metric world landmarks.

    Supported poses: open_palm, fist, pinch_index, pinch_middle, pinch_ring,
    v_sign, shaka, extension_ramp.
    """
    pts = np.zeros((21, 3), dtype=np.float32)
    for idx, coords in BASE_WORLD_LM.items():
        pts[idx] = coords

    # Mirror X for left hand
    if side == Side.LEFT:
        pts[:, 0] = -pts[:, 0]

    # Articulate finger flexion depending on pose
    def curl_finger(mcp: int, pip: int, dip: int, tip: int, amount: float) -> None:
        # Amount: 0.0 = straight, 1.0 = curled into palm
        ang1 = amount * math.radians(50)
        ang2 = ang1 + amount * math.radians(90)
        ang3 = ang2 + amount * math.radians(90)
        l_pip = float(np.linalg.norm(pts[pip] - pts[mcp]))
        l_dip = float(np.linalg.norm(pts[dip] - pts[pip]))
        l_tip = float(np.linalg.norm(pts[tip] - pts[dip]))
        pts[pip] = pts[mcp] + np.array(
            [0, l_pip * math.cos(ang1), l_pip * math.sin(ang1)], dtype=np.float32
        )
        pts[dip] = pts[pip] + np.array(
            [0, l_dip * math.cos(ang2), l_dip * math.sin(ang2)], dtype=np.float32
        )
        pts[tip] = pts[dip] + np.array(
            [0, l_tip * math.cos(ang3), l_tip * math.sin(ang3)], dtype=np.float32
        )

    def curl_thumb(amount: float) -> None:
        # Curl thumb towards index MCP
        target = pts[Lm.INDEX_FINGER_MCP]
        pts[Lm.THUMB_IP] = pts[Lm.THUMB_IP] * (1.0 - 0.7 * amount) + target * (0.7 * amount)
        pts[Lm.THUMB_TIP] = pts[Lm.THUMB_TIP] * (1.0 - 0.9 * amount) + target * (0.9 * amount)

    if pose == "open_palm":
        pass  # already straight
    elif pose == "fist":
        curl_finger(
            Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP, 1.0
        )
        curl_finger(
            Lm.MIDDLE_FINGER_MCP,
            Lm.MIDDLE_FINGER_PIP,
            Lm.MIDDLE_FINGER_DIP,
            Lm.MIDDLE_FINGER_TIP,
            1.0,
        )
        curl_finger(
            Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP, 1.0
        )
        curl_finger(Lm.PINKY_MCP, Lm.PINKY_PIP, Lm.PINKY_DIP, Lm.PINKY_TIP, 1.0)
        curl_thumb(0.9)
    elif pose == "pinch_index":
        # Thumb tip and index tip touch
        touch_pt = 0.5 * (pts[Lm.THUMB_TIP] + pts[Lm.INDEX_FINGER_TIP])
        pts[Lm.THUMB_TIP] = touch_pt
        pts[Lm.INDEX_FINGER_TIP] = touch_pt + np.array([0.005, 0.005, 0.0], dtype=np.float32)
        pts[Lm.INDEX_FINGER_DIP] = touch_pt + np.array([0.01, -0.02, 0.01], dtype=np.float32)
    elif pose == "pinch_middle":
        touch_pt = 0.5 * (pts[Lm.THUMB_TIP] + pts[Lm.MIDDLE_FINGER_TIP])
        pts[Lm.THUMB_TIP] = touch_pt
        pts[Lm.MIDDLE_FINGER_TIP] = touch_pt + np.array([0.005, 0.005, 0.0], dtype=np.float32)
    elif pose == "pinch_ring":
        touch_pt = 0.5 * (pts[Lm.THUMB_TIP] + pts[Lm.RING_FINGER_TIP])
        pts[Lm.THUMB_TIP] = touch_pt
        pts[Lm.RING_FINGER_TIP] = touch_pt + np.array([0.005, 0.005, 0.0], dtype=np.float32)
    elif pose == "v_sign":
        # Index and middle straight & spread; ring, pinky, thumb curled
        pts[Lm.INDEX_FINGER_TIP, 0] += 0.02 if side == Side.RIGHT else -0.02
        pts[Lm.MIDDLE_FINGER_TIP, 0] -= 0.02 if side == Side.RIGHT else -0.02
        curl_finger(
            Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP, 1.0
        )
        curl_finger(Lm.PINKY_MCP, Lm.PINKY_PIP, Lm.PINKY_DIP, Lm.PINKY_TIP, 1.0)
        curl_thumb(0.8)
    elif pose == "shaka":
        # Thumb and pinky extended; index, middle, ring curled
        curl_finger(
            Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP, 1.0
        )
        curl_finger(
            Lm.MIDDLE_FINGER_MCP,
            Lm.MIDDLE_FINGER_PIP,
            Lm.MIDDLE_FINGER_DIP,
            Lm.MIDDLE_FINGER_TIP,
            1.0,
        )
        curl_finger(
            Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP, 1.0
        )
    elif pose == "extension_ramp":
        amt = 1.0 - (extension_ramp if extension_ramp is not None else 0.5)
        curl_finger(
            Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP, amt
        )

    # In-plane rotation
    if abs(roll_deg) > 1e-3:
        pts = _rotate_z(pts, math.radians(roll_deg))

    world_lm = pts.copy()

    # Image coordinates: centered at center_xy, scaled by palm_scale
    # In image coordinates, y increases downwards!
    img_lm = np.zeros((21, 3), dtype=np.float32)
    img_lm[:, 0] = center_xy[0] + (pts[:, 0] / 0.12) * palm_scale / aspect
    img_lm[:, 1] = center_xy[1] - (pts[:, 1] / 0.12) * palm_scale
    img_lm[:, 2] = pts[:, 2] / 0.12 * palm_scale

    if noise_sigma > 0:
        noise = np.random.normal(0, noise_sigma, img_lm.shape).astype(np.float32)
        img_lm += noise
        world_noise = np.random.normal(0, noise_sigma * 0.12, world_lm.shape).astype(np.float32)
        world_lm += world_noise

    return img_lm, world_lm


def generate_replay_fixture(
    fixture_name: str,
    output_path: Path,
    fps: int = 60,
    duration_s: float = 1.0,
) -> None:
    """Generate a specific named replay fixture with embedded expect statements."""
    total_frames = int(fps * duration_s)
    dt_ns = int(1_000_000_000 // fps)

    with ReplayWriter(
        output_path, fps_nominal=fps, notes=f"Synthesized fixture: {fixture_name}"
    ) as writer:
        if fixture_name == "move_slow":
            # Smooth diagonal cursor drift
            for i in range(total_frames):
                t_ns = i * dt_ns
                t = i / total_frames
                cx = 0.4 + 0.2 * t
                cy = 0.4 + 0.2 * t
                lm, world = generate_hand_landmarks("open_palm", Side.RIGHT, center_xy=(cx, cy))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )

        elif fixture_name == "move_fast":
            for i in range(total_frames):
                t_ns = i * dt_ns
                t = i / total_frames
                cx = 0.3 + 0.4 * math.sin(t * math.pi)
                cy = 0.5 + 0.2 * math.cos(t * math.pi)
                lm, world = generate_hand_landmarks("open_palm", Side.RIGHT, center_xy=(cx, cy))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )

        elif fixture_name == "pinch_click":
            # 0.3s open, 0.1s pinch-index, 0.6s open -> produces CLICK_LEFT
            pinch_start = int(0.3 * fps)
            pinch_end = int(0.42 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                pose = "pinch_index" if pinch_start <= i <= pinch_end else "open_palm"
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == pinch_end + 1:
                    writer.write_expect(t_ns, "CLICK_LEFT")

        elif fixture_name == "pinch_drag":
            # Pinch hold > 300 ms -> DRAG_START, hold, release -> DRAG_END
            pinch_start = int(0.2 * fps)
            pinch_end = int(0.8 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                pose = "pinch_index" if pinch_start <= i <= pinch_end else "open_palm"
                cx = 0.5 + 0.1 * (i / total_frames)
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(cx, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == pinch_start + int(0.3 * fps):
                    writer.write_expect(t_ns, "DRAG_START")
                elif i == pinch_end + 1:
                    writer.write_expect(t_ns, "DRAG_END")

        elif fixture_name == "double_click":
            # Two quick taps within 350 ms
            tap1_start, tap1_end = int(0.2 * fps), int(0.28 * fps)
            tap2_start, tap2_end = int(0.42 * fps), int(0.50 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                is_pinching = (tap1_start <= i <= tap1_end) or (tap2_start <= i <= tap2_end)
                pose = "pinch_index" if is_pinching else "open_palm"
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == tap2_end + 1:
                    writer.write_expect(t_ns, "DOUBLE_CLICK")

        elif fixture_name == "right_click_vs_left":
            # Middle-finger pinch tap -> CLICK_RIGHT
            pinch_start = int(0.3 * fps)
            pinch_end = int(0.42 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                pose = "pinch_middle" if pinch_start <= i <= pinch_end else "open_palm"
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == pinch_end + 1:
                    writer.write_expect(t_ns, "CLICK_RIGHT")

        elif fixture_name == "scroll_vsign":
            # V-sign hold + displacement
            v_start = int(0.2 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                pose = "v_sign" if i >= v_start else "open_palm"
                cy = (
                    0.5 - 0.15 * ((i - v_start) / (total_frames - v_start)) if i >= v_start else 0.5
                )
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(0.5, cy))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == v_start + int(0.12 * fps):
                    writer.write_expect(t_ns, "SCROLL_START")

        elif fixture_name == "zoom_two_hand":
            # Two hands pinching, moving apart
            zoom_start = int(0.2 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                spacing = 0.15 + 0.2 * (i / total_frames) if i >= zoom_start else 0.15
                pose = "pinch_index" if i >= zoom_start else "open_palm"
                lm_l, world_l = generate_hand_landmarks(
                    pose, Side.LEFT, center_xy=(0.5 - spacing / 2, 0.5)
                )
                lm_r, world_r = generate_hand_landmarks(
                    pose, Side.RIGHT, center_xy=(0.5 + spacing / 2, 0.5)
                )
                hl = Hand(side=Side.LEFT, score=0.98, lm=lm_l, world=world_l)
                hr = Hand(side=Side.RIGHT, score=0.98, lm=lm_r, world=world_r)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(hl, hr))
                )
                if i == zoom_start + int(0.08 * fps):
                    writer.write_expect(t_ns, "ZOOM_START")

        elif fixture_name == "clutch_resume":
            # Open palm -> fist hold 400ms (CLUTCH) -> open palm hold 400ms (RESUME)
            fist_start = int(0.2 * fps)
            fist_end = int(0.8 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                pose = "fist" if fist_start <= i <= fist_end else "open_palm"
                lm, world = generate_hand_landmarks(pose, Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )
                if i == fist_start + int(0.4 * fps):
                    writer.write_expect(t_ns, "CLUTCH")
                elif i == fist_end + int(0.4 * fps):
                    writer.write_expect(t_ns, "RESUME")

        elif fixture_name == "hand_exit_enter":
            # Hand present -> disappears for 200ms -> reappears
            exit_f = int(0.3 * fps)
            enter_f = int(0.6 * fps)
            for i in range(total_frames):
                t_ns = i * dt_ns
                if exit_f <= i < enter_f:
                    hands = ()
                else:
                    lm, world = generate_hand_landmarks(
                        "open_palm", Side.RIGHT, center_xy=(0.5, 0.5)
                    )
                    hands = (Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world),)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=hands)
                )

        elif fixture_name == "occlusion_partial":
            # Score drops below min_hand_conf (0.6)
            for i in range(total_frames):
                t_ns = i * dt_ns
                score = 0.35 if int(0.3 * fps) <= i <= int(0.6 * fps) else 0.95
                lm, world = generate_hand_landmarks("open_palm", Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=score, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )

        elif fixture_name == "both_handedness":
            # Alternate left hand then right hand
            for i in range(total_frames):
                t_ns = i * dt_ns
                side = Side.LEFT if i < total_frames // 2 else Side.RIGHT
                cx = 0.35 if side == Side.LEFT else 0.65
                lm, world = generate_hand_landmarks("open_palm", side, center_xy=(cx, 0.5))
                h = Hand(side=side, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )

        elif fixture_name == "yoke_turns":
            # Two hands turning left then right like a steering wheel
            for i in range(total_frames):
                t_ns = i * dt_ns
                t = i / total_frames
                steer_angle = 35.0 * math.sin(t * 2 * math.pi)
                # Left hand and right hand rotate on steering wheel rim
                rad = math.radians(steer_angle)
                r = 0.20
                xl, yl = 0.5 - r * math.cos(rad), 0.5 + r * math.sin(rad)
                xr, yr = 0.5 + r * math.cos(rad), 0.5 - r * math.sin(rad)
                lm_l, world_l = generate_hand_landmarks(
                    "fist", Side.LEFT, center_xy=(xl, yl), roll_deg=-steer_angle
                )
                lm_r, world_r = generate_hand_landmarks(
                    "fist", Side.RIGHT, center_xy=(xr, yr), roll_deg=-steer_angle
                )
                hl = Hand(side=Side.LEFT, score=0.98, lm=lm_l, world=world_l)
                hr = Hand(side=Side.RIGHT, score=0.98, lm=lm_r, world=world_r)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(hl, hr))
                )

        elif fixture_name == "trigger_ramp":
            # Finger extension ramping from 0.0 to 1.0 (throttle trigger)
            for i in range(total_frames):
                t_ns = i * dt_ns
                ramp = i / total_frames
                lm, world = generate_hand_landmarks(
                    "extension_ramp", Side.RIGHT, center_xy=(0.5, 0.5), extension_ramp=ramp
                )
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )

        elif fixture_name == "two_people":
            # Primary hand engaged, secondary hand enters background with smaller palm_size
            for i in range(total_frames):
                t_ns = i * dt_ns
                lm1, w1 = generate_hand_landmarks(
                    "open_palm", Side.RIGHT, center_xy=(0.4, 0.5), palm_scale=0.18
                )
                h1 = Hand(side=Side.RIGHT, score=0.98, lm=lm1, world=w1)
                hands = [h1]
                if i > int(0.25 * fps):
                    lm2, w2 = generate_hand_landmarks(
                        "open_palm", Side.RIGHT, center_xy=(0.8, 0.3), palm_scale=0.08
                    )
                    h2 = Hand(side=Side.RIGHT, score=0.92, lm=lm2, world=w2)
                    hands.append(h2)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=tuple(hands))
                )

        else:
            # Default open palm
            for i in range(total_frames):
                t_ns = i * dt_ns
                lm, world = generate_hand_landmarks("open_palm", Side.RIGHT, center_xy=(0.5, 0.5))
                h = Hand(side=Side.RIGHT, score=0.98, lm=lm, world=world)
                writer.write_frame(
                    HandFrame(t_capture_ns=t_ns, t_infer_done_ns=t_ns, seq=i, hands=(h,))
                )


ALL_STANDARD_FIXTURES = [
    ("move_slow", 1.0),
    ("move_fast", 1.0),
    ("pinch_click", 1.0),
    ("pinch_drag", 1.2),
    ("double_click", 1.0),
    ("right_click_vs_left", 1.0),
    ("scroll_vsign", 1.2),
    ("zoom_two_hand", 1.2),
    ("clutch_resume", 1.8),
    ("hand_exit_enter", 1.2),
    ("occlusion_partial", 1.0),
    ("both_handedness", 1.0),
    ("yoke_turns", 1.5),
    ("trigger_ramp", 1.2),
    ("two_people", 1.2),
]


def generate_all_fixtures(output_dir: Path | str = "tests/replay") -> None:
    """Generate all standard testing replay fixtures."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, dur in ALL_STANDARD_FIXTURES:
        dest = out / f"{name}.jsonl"
        generate_replay_fixture(name, dest, fps=60, duration_s=dur)
        print(f"Generated replay fixture: {dest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Synthetic Hand Landmark Generator")
    parser.add_argument(
        "--all", action="store_true", help="Generate all standard fixtures in tests/replay/"
    )
    parser.add_argument(
        "--fixture", type=str, default="pinch_click", help="Name of specific fixture to generate"
    )
    parser.add_argument(
        "--out", type=str, default="tests/replay/output.jsonl", help="Output JSONL path"
    )
    parser.add_argument("--duration", type=float, default=1.0, help="Duration in seconds")
    parser.add_argument("--fps", type=int, default=60, help="Framerate")

    args = parser.parse_args()
    if args.all:
        generate_all_fixtures()
    else:
        generate_replay_fixture(
            args.fixture, Path(args.out), fps=args.fps, duration_s=args.duration
        )
        print(f"Generated fixture {args.fixture} -> {args.out}")
