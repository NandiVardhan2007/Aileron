"""Pure geometric feature extraction from hand landmarks per SIGNAL_PROCESSING.md."""

import math

import numpy as np

from aileron.config import FingersConfig, TrackingConfig
from aileron.interfaces import Hand, HandFeatures
from aileron.landmarks import Lm

MIN_VECTOR_NORM = 1e-6


def _compute_angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """Compute the angle ABC in degrees with vertex at B."""
    ba = a - b
    bc = c - b
    norm_ba = float(np.linalg.norm(ba))
    norm_bc = float(np.linalg.norm(bc))
    if norm_ba < MIN_VECTOR_NORM or norm_bc < MIN_VECTOR_NORM:
        return 180.0
    dot = float(np.dot(ba, bc))
    cos_theta = dot / (norm_ba * norm_bc)
    cos_theta = max(-1.0, min(1.0, cos_theta))
    return math.degrees(math.acos(cos_theta))


def compute_palm_size(lm: np.ndarray, aspect: float = 16.0 / 9.0) -> float:
    """Compute aspect-corrected palm size in normalized image coordinates."""
    # Palm size = 1/2 * (||L0 - L9|| + ||L5 - L17||)
    dx1 = (lm[int(Lm.WRIST), 0] - lm[int(Lm.MIDDLE_FINGER_MCP), 0]) * aspect
    dy1 = lm[int(Lm.WRIST), 1] - lm[int(Lm.MIDDLE_FINGER_MCP), 1]
    d1 = math.hypot(dx1, dy1)

    dx2 = (lm[int(Lm.INDEX_FINGER_MCP), 0] - lm[int(Lm.PINKY_MCP), 0]) * aspect
    dy2 = lm[int(Lm.INDEX_FINGER_MCP), 1] - lm[int(Lm.PINKY_MCP), 1]
    d2 = math.hypot(dx2, dy2)

    return 0.5 * (d1 + d2)


def compute_finger_curls(
    world_lm: np.ndarray,
    fingers_cfg: FingersConfig,
    palm_size_world: float,
) -> dict[str, float]:
    """Compute extension values [0.0 (curled) .. 1.0 (straight)] for each finger."""
    curled = fingers_cfg.theta_curled_deg
    straight = fingers_cfg.theta_straight_deg
    span = max(1.0, straight - curled)

    def angle_to_ext(theta: float) -> float:
        return max(0.0, min(1.0, (theta - curled) / span))

    # Index
    th_pip_idx = _compute_angle_deg(
        world_lm[int(Lm.INDEX_FINGER_MCP)],
        world_lm[int(Lm.INDEX_FINGER_PIP)],
        world_lm[int(Lm.INDEX_FINGER_DIP)],
    )
    th_dip_idx = _compute_angle_deg(
        world_lm[int(Lm.INDEX_FINGER_PIP)],
        world_lm[int(Lm.INDEX_FINGER_DIP)],
        world_lm[int(Lm.INDEX_FINGER_TIP)],
    )
    ext_idx = angle_to_ext(0.5 * (th_pip_idx + th_dip_idx))

    # Middle
    th_pip_mid = _compute_angle_deg(
        world_lm[int(Lm.MIDDLE_FINGER_MCP)],
        world_lm[int(Lm.MIDDLE_FINGER_PIP)],
        world_lm[int(Lm.MIDDLE_FINGER_DIP)],
    )
    th_dip_mid = _compute_angle_deg(
        world_lm[int(Lm.MIDDLE_FINGER_PIP)],
        world_lm[int(Lm.MIDDLE_FINGER_DIP)],
        world_lm[int(Lm.MIDDLE_FINGER_TIP)],
    )
    ext_mid = angle_to_ext(0.5 * (th_pip_mid + th_dip_mid))

    # Ring
    th_pip_rng = _compute_angle_deg(
        world_lm[int(Lm.RING_FINGER_MCP)],
        world_lm[int(Lm.RING_FINGER_PIP)],
        world_lm[int(Lm.RING_FINGER_DIP)],
    )
    th_dip_rng = _compute_angle_deg(
        world_lm[int(Lm.RING_FINGER_PIP)],
        world_lm[int(Lm.RING_FINGER_DIP)],
        world_lm[int(Lm.RING_FINGER_TIP)],
    )
    ext_rng = angle_to_ext(0.5 * (th_pip_rng + th_dip_rng))

    # Pinky
    th_pip_pnk = _compute_angle_deg(
        world_lm[int(Lm.PINKY_MCP)],
        world_lm[int(Lm.PINKY_PIP)],
        world_lm[int(Lm.PINKY_DIP)],
    )
    th_dip_pnk = _compute_angle_deg(
        world_lm[int(Lm.PINKY_PIP)],
        world_lm[int(Lm.PINKY_DIP)],
        world_lm[int(Lm.PINKY_TIP)],
    )
    ext_pnk = angle_to_ext(0.5 * (th_pip_pnk + th_dip_pnk))

    # Thumb: angle at MCP and IP plus distance from thumb tip to index MCP
    th_mcp_tmb = _compute_angle_deg(
        world_lm[int(Lm.THUMB_CMC)],
        world_lm[int(Lm.THUMB_MCP)],
        world_lm[int(Lm.THUMB_IP)],
    )
    th_ip_tmb = _compute_angle_deg(
        world_lm[int(Lm.THUMB_MCP)],
        world_lm[int(Lm.THUMB_IP)],
        world_lm[int(Lm.THUMB_TIP)],
    )
    tmb_angle_ext = angle_to_ext(0.5 * (th_mcp_tmb + th_ip_tmb))

    tmb_tip_dist = float(
        np.linalg.norm(world_lm[int(Lm.THUMB_TIP)] - world_lm[int(Lm.INDEX_FINGER_MCP)])
    )
    norm_dist = tmb_tip_dist / max(MIN_VECTOR_NORM, palm_size_world)
    tmb_dist_ext = max(0.0, min(1.0, (norm_dist - 0.25) / 0.40))
    ext_tmb = 0.5 * (tmb_angle_ext + tmb_dist_ext)

    return {
        "thumb": float(np.clip(ext_tmb, 0.0, 1.0)),
        "index": float(np.clip(ext_idx, 0.0, 1.0)),
        "middle": float(np.clip(ext_mid, 0.0, 1.0)),
        "ring": float(np.clip(ext_rng, 0.0, 1.0)),
        "pinky": float(np.clip(ext_pnk, 0.0, 1.0)),
    }


def compute_pinch_ratios(
    world_lm: np.ndarray,
    img_lm: np.ndarray,
    palm_size_img: float,
    aspect: float = 16.0 / 9.0,
) -> dict[str, float]:
    """Compute scale-invariant distance from thumb tip to each fingertip."""
    # Preferred: world metric coordinates
    d_world_w9 = float(
        np.linalg.norm(world_lm[int(Lm.WRIST)] - world_lm[int(Lm.MIDDLE_FINGER_MCP)])
    )
    d_world_517 = float(
        np.linalg.norm(world_lm[int(Lm.INDEX_FINGER_MCP)] - world_lm[int(Lm.PINKY_MCP)])
    )
    palm_world = 0.5 * (d_world_w9 + d_world_517)

    if palm_world > MIN_VECTOR_NORM:
        thumb_tip = world_lm[int(Lm.THUMB_TIP)]
        d_idx = float(np.linalg.norm(thumb_tip - world_lm[int(Lm.INDEX_FINGER_TIP)]))
        d_mid = float(np.linalg.norm(thumb_tip - world_lm[int(Lm.MIDDLE_FINGER_TIP)]))
        d_rng = float(np.linalg.norm(thumb_tip - world_lm[int(Lm.RING_FINGER_TIP)]))
        d_pnk = float(np.linalg.norm(thumb_tip - world_lm[int(Lm.PINKY_TIP)]))
        return {
            "index": d_idx / palm_world,
            "middle": d_mid / palm_world,
            "ring": d_rng / palm_world,
            "pinky": d_pnk / palm_world,
        }

    # Fallback to image-normalized 2D distance
    t_pt = img_lm[int(Lm.THUMB_TIP)]

    def dist2d(pt: np.ndarray) -> float:
        dx = (t_pt[0] - pt[0]) * aspect
        dy = t_pt[1] - pt[1]
        return math.hypot(dx, dy) / max(MIN_VECTOR_NORM, palm_size_img)

    return {
        "index": dist2d(img_lm[int(Lm.INDEX_FINGER_TIP)]),
        "middle": dist2d(img_lm[int(Lm.MIDDLE_FINGER_TIP)]),
        "ring": dist2d(img_lm[int(Lm.RING_FINGER_TIP)]),
        "pinky": dist2d(img_lm[int(Lm.PINKY_TIP)]),
    }


def compute_roll_deg(
    world_lm: np.ndarray,
    img_lm: np.ndarray,
    aspect: float = 16.0 / 9.0,
) -> float:
    """Compute hand roll in degrees (0 = fingers up, positive = tilted right)."""
    v_world = world_lm[int(Lm.MIDDLE_FINGER_MCP)] - world_lm[int(Lm.WRIST)]
    if float(np.linalg.norm(v_world)) > MIN_VECTOR_NORM:
        # In world space: x is right, y is up
        return math.degrees(math.atan2(float(v_world[0]), float(v_world[1])))

    # Fallback to 2D image coordinates (y is down)
    dx = (img_lm[int(Lm.MIDDLE_FINGER_MCP), 0] - img_lm[int(Lm.WRIST), 0]) * aspect
    dy = -(img_lm[int(Lm.MIDDLE_FINGER_MCP), 1] - img_lm[int(Lm.WRIST), 1])
    return math.degrees(math.atan2(dx, dy))


def compute_palm_normal(world_lm: np.ndarray, is_right: bool) -> np.ndarray:
    """Compute unit normal vector perpendicular to the palm."""
    v1 = world_lm[int(Lm.INDEX_FINGER_MCP)] - world_lm[int(Lm.WRIST)]
    v2 = world_lm[int(Lm.PINKY_MCP)] - world_lm[int(Lm.WRIST)]

    cross = np.cross(v1, v2) if is_right else np.cross(v2, v1)
    norm = float(np.linalg.norm(cross))
    if norm < MIN_VECTOR_NORM:
        return np.array([0.0, 0.0, 1.0], dtype=np.float32)
    return (cross / norm).astype(np.float32)


def extract_features(
    hand: Hand,
    tracking_cfg: TrackingConfig,
    fingers_cfg: FingersConfig,
    aspect: float = 16.0 / 9.0,
) -> HandFeatures:
    """Pure, deterministic feature extraction from a single Hand."""
    # Check for NaNs or non-finite numbers
    if not np.all(np.isfinite(hand.lm)) or not np.all(np.isfinite(hand.world)):
        return HandFeatures(
            side=hand.side,
            valid=False,
            palm_size=0.0,
            anchor=(0.5, 0.5),
            curl={"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            pinch={"index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            roll_deg=0.0,
            palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            palm_center=(0.5, 0.5),
        )

    palm_size = compute_palm_size(hand.lm, aspect=aspect)
    if palm_size < tracking_cfg.min_palm_size:
        return HandFeatures(
            side=hand.side,
            valid=False,
            palm_size=palm_size,
            anchor=(
                float(hand.lm[int(Lm.INDEX_FINGER_MCP), 0]),
                float(hand.lm[int(Lm.INDEX_FINGER_MCP), 1]),
            ),
            curl={"thumb": 0.0, "index": 0.0, "middle": 0.0, "ring": 0.0, "pinky": 0.0},
            pinch={"index": 1.0, "middle": 1.0, "ring": 1.0, "pinky": 1.0},
            roll_deg=0.0,
            palm_normal=np.array([0.0, 0.0, 1.0], dtype=np.float32),
            palm_center=(0.5, 0.5),
        )

    # Anchor = midpoint(INDEX_MCP, MIDDLE_MCP) per ADR-003
    anchor_x = float(
        0.5 * (hand.lm[int(Lm.INDEX_FINGER_MCP), 0] + hand.lm[int(Lm.MIDDLE_FINGER_MCP), 0])
    )
    anchor_y = float(
        0.5 * (hand.lm[int(Lm.INDEX_FINGER_MCP), 1] + hand.lm[int(Lm.MIDDLE_FINGER_MCP), 1])
    )

    # Palm center = midpoint(WRIST, MIDDLE_MCP)
    center_x = float(0.5 * (hand.lm[int(Lm.WRIST), 0] + hand.lm[int(Lm.MIDDLE_FINGER_MCP), 0]))
    center_y = float(0.5 * (hand.lm[int(Lm.WRIST), 1] + hand.lm[int(Lm.MIDDLE_FINGER_MCP), 1]))

    # World palm size for 3D normalization
    d_w9 = float(np.linalg.norm(hand.world[int(Lm.WRIST)] - hand.world[int(Lm.MIDDLE_FINGER_MCP)]))
    d_517 = float(
        np.linalg.norm(hand.world[int(Lm.INDEX_FINGER_MCP)] - hand.world[int(Lm.PINKY_MCP)])
    )
    palm_size_world = 0.5 * (d_w9 + d_517)

    curls = compute_finger_curls(hand.world, fingers_cfg, palm_size_world)
    pinches = compute_pinch_ratios(hand.world, hand.lm, palm_size, aspect=aspect)
    roll = compute_roll_deg(hand.world, hand.lm, aspect=aspect)
    is_right = hand.side.value == "right"
    normal = compute_palm_normal(hand.world, is_right)

    # V-sign gap: distance between index tip and middle tip normalized by palm size
    d_v_tips = float(
        np.linalg.norm(hand.world[int(Lm.INDEX_FINGER_TIP)] - hand.world[int(Lm.MIDDLE_FINGER_TIP)])
    )
    v_gap = float(d_v_tips / max(1e-4, palm_size_world))

    return HandFeatures(
        side=hand.side,
        valid=True,
        palm_size=palm_size,
        anchor=(anchor_x, anchor_y),
        curl=curls,
        pinch=pinches,
        roll_deg=roll,
        palm_normal=normal,
        palm_center=(center_x, center_y),
        v_gap=v_gap,
    )
