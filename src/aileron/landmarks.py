"""MediaPipe 21-point hand landmark definitions and named constants."""

from enum import IntEnum


class Lm(IntEnum):
    """Named constants for MediaPipe 21 hand landmarks."""

    WRIST = 0

    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4

    INDEX_FINGER_MCP = 5
    INDEX_FINGER_PIP = 6
    INDEX_FINGER_DIP = 7
    INDEX_FINGER_TIP = 8

    MIDDLE_FINGER_MCP = 9
    MIDDLE_FINGER_PIP = 10
    MIDDLE_FINGER_DIP = 11
    MIDDLE_FINGER_TIP = 12

    RING_FINGER_MCP = 13
    RING_FINGER_PIP = 14
    RING_FINGER_DIP = 15
    RING_FINGER_TIP = 16

    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


FINGER_CHAINS: dict[str, tuple[Lm, Lm, Lm, Lm]] = {
    "thumb": (Lm.THUMB_CMC, Lm.THUMB_MCP, Lm.THUMB_IP, Lm.THUMB_TIP),
    "index": (Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP),
    "middle": (
        Lm.MIDDLE_FINGER_MCP,
        Lm.MIDDLE_FINGER_PIP,
        Lm.MIDDLE_FINGER_DIP,
        Lm.MIDDLE_FINGER_TIP,
    ),
    "ring": (Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP),
    "pinky": (Lm.PINKY_MCP, Lm.PINKY_PIP, Lm.PINKY_DIP, Lm.PINKY_TIP),
}

HAND_CONNECTIONS: tuple[tuple[Lm, Lm], ...] = (
    # Palm
    (Lm.WRIST, Lm.THUMB_CMC),
    (Lm.WRIST, Lm.INDEX_FINGER_MCP),
    (Lm.INDEX_FINGER_MCP, Lm.MIDDLE_FINGER_MCP),
    (Lm.MIDDLE_FINGER_MCP, Lm.RING_FINGER_MCP),
    (Lm.RING_FINGER_MCP, Lm.PINKY_MCP),
    (Lm.WRIST, Lm.PINKY_MCP),
    # Thumb
    (Lm.THUMB_CMC, Lm.THUMB_MCP),
    (Lm.THUMB_MCP, Lm.THUMB_IP),
    (Lm.THUMB_IP, Lm.THUMB_TIP),
    # Index
    (Lm.INDEX_FINGER_MCP, Lm.INDEX_FINGER_PIP),
    (Lm.INDEX_FINGER_PIP, Lm.INDEX_FINGER_DIP),
    (Lm.INDEX_FINGER_DIP, Lm.INDEX_FINGER_TIP),
    # Middle
    (Lm.MIDDLE_FINGER_MCP, Lm.MIDDLE_FINGER_PIP),
    (Lm.MIDDLE_FINGER_PIP, Lm.MIDDLE_FINGER_DIP),
    (Lm.MIDDLE_FINGER_DIP, Lm.MIDDLE_FINGER_TIP),
    # Ring
    (Lm.RING_FINGER_MCP, Lm.RING_FINGER_PIP),
    (Lm.RING_FINGER_PIP, Lm.RING_FINGER_DIP),
    (Lm.RING_FINGER_DIP, Lm.RING_FINGER_TIP),
    # Pinky
    (Lm.PINKY_MCP, Lm.PINKY_PIP),
    (Lm.PINKY_PIP, Lm.PINKY_DIP),
    (Lm.PINKY_DIP, Lm.PINKY_TIP),
)
