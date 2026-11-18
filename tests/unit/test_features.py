"""Unit tests for geometric feature extraction."""

import numpy as np

from aileron.config import FingersConfig, TrackingConfig
from aileron.features.extraction import (
    compute_finger_curls,
    compute_palm_size,
    compute_pinch_ratios,
    extract_features,
)
from aileron.interfaces import Hand, Side
from aileron.landmarks import Lm


def test_palm_size_scaling_and_translation() -> None:
    """Verify palm_size is invariant to translation and scales linearly."""
    lm = np.zeros((21, 3), dtype=np.float32)
    lm[int(Lm.WRIST)] = [0.5, 0.6, 0.0]
    lm[int(Lm.MIDDLE_FINGER_MCP)] = [0.5, 0.4, 0.0]
    lm[int(Lm.INDEX_FINGER_MCP)] = [0.45, 0.4, 0.0]
    lm[int(Lm.PINKY_MCP)] = [0.55, 0.4, 0.0]

    base_size = compute_palm_size(lm, aspect=1.0)
    assert base_size > 0.0

    # Translate
    lm_trans = lm + np.array([0.2, -0.1, 0.0], dtype=np.float32)
    trans_size = compute_palm_size(lm_trans, aspect=1.0)
    assert abs(base_size - trans_size) < 1e-5

    # Scale by 2.0
    lm_scaled = lm * 2.0
    scaled_size = compute_palm_size(lm_scaled, aspect=1.0)
    assert abs(scaled_size - 2.0 * base_size) < 1e-4


def test_curls_open_vs_curled() -> None:
    """Verify finger curl extension is ~1.0 for straight finger and ~0.0 for curled."""
    cfg = FingersConfig()
    world = np.zeros((21, 3), dtype=np.float32)

    # Straight index finger
    world[int(Lm.INDEX_FINGER_MCP)] = [0.03, 0.10, 0.0]
    world[int(Lm.INDEX_FINGER_PIP)] = [0.03, 0.14, 0.0]
    world[int(Lm.INDEX_FINGER_DIP)] = [0.03, 0.17, 0.0]
    world[int(Lm.INDEX_FINGER_TIP)] = [0.03, 0.20, 0.0]

    curls = compute_finger_curls(world, cfg, palm_size_world=0.10)
    assert curls["index"] > 0.90

    # Curled index finger (bent 90 degrees at PIP and DIP)
    world[int(Lm.INDEX_FINGER_PIP)] = [0.03, 0.14, 0.0]
    world[int(Lm.INDEX_FINGER_DIP)] = [0.03, 0.14, 0.03]
    world[int(Lm.INDEX_FINGER_TIP)] = [0.03, 0.11, 0.03]

    curls_curled = compute_finger_curls(world, cfg, palm_size_world=0.10)
    assert curls_curled["index"] < 0.25


def test_pinch_ratios() -> None:
    """Verify pinch ratio drops below 0.25 when tips touch."""
    world = np.zeros((21, 3), dtype=np.float32)
    img = np.zeros((21, 3), dtype=np.float32)

    # Wrist to MCP defines palm size ~0.10
    world[int(Lm.WRIST)] = [0.0, 0.0, 0.0]
    world[int(Lm.MIDDLE_FINGER_MCP)] = [0.0, 0.10, 0.0]
    world[int(Lm.INDEX_FINGER_MCP)] = [0.03, 0.10, 0.0]
    world[int(Lm.PINKY_MCP)] = [-0.03, 0.10, 0.0]

    # Thumb tip and index tip touch
    world[int(Lm.THUMB_TIP)] = [0.03, 0.15, 0.0]
    world[int(Lm.INDEX_FINGER_TIP)] = [0.031, 0.151, 0.0]

    ratios = compute_pinch_ratios(world, img, palm_size_img=0.10)
    assert ratios["index"] < 0.20


def test_degenerate_hand_features() -> None:
    """Verify NaN / non-finite inputs return valid=False without raising."""
    nan_lm = np.full((21, 3), np.nan, dtype=np.float32)
    world = np.zeros((21, 3), dtype=np.float32)
    hand = Hand(side=Side.RIGHT, score=0.9, lm=nan_lm, world=world)

    feats = extract_features(hand, TrackingConfig(), FingersConfig())
    assert feats.valid is False
