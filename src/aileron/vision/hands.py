"""Hand processing and handedness resolution."""

import numpy as np

from aileron.interfaces import Hand, Side


def resolve_handedness(raw_label: str, is_mirrored: bool = True) -> Side:
    """Resolve MediaPipe handedness label to user's point of view.

    MediaPipe's raw model classifies from the camera's perspective.
    When frames are mirrored horizontally at capture, a user's right hand
    visually appears as a left hand to the model.
    """
    label_lower = raw_label.lower()
    if is_mirrored:
        # If camera is mirrored, invert the model's reported label
        return Side.RIGHT if "left" in label_lower else Side.LEFT
    else:
        return Side.LEFT if "left" in label_lower else Side.RIGHT


def parse_hand(
    category_label: str,
    score: float,
    landmarks_list: list[object],
    world_landmarks_list: list[object],
    is_mirrored: bool = True,
) -> Hand:
    """Convert MediaPipe category and landmark objects into an immutable Hand instance."""
    side = resolve_handedness(category_label, is_mirrored=is_mirrored)

    lm_arr = np.zeros((21, 3), dtype=np.float32)
    for i, pt in enumerate(landmarks_list):
        lm_arr[i, 0] = getattr(pt, "x", 0.0)
        lm_arr[i, 1] = getattr(pt, "y", 0.0)
        lm_arr[i, 2] = getattr(pt, "z", 0.0)

    world_arr = np.zeros((21, 3), dtype=np.float32)
    for i, pt in enumerate(world_landmarks_list):
        world_arr[i, 0] = getattr(pt, "x", 0.0)
        world_arr[i, 1] = getattr(pt, "y", 0.0)
        world_arr[i, 2] = getattr(pt, "z", 0.0)

    return Hand(
        side=side,
        score=float(score),
        lm=lm_arr,
        world=world_arr,
    )
