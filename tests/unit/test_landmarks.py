"""Unit tests for landmark constants and finger chains."""

from aileron.landmarks import FINGER_CHAINS, HAND_CONNECTIONS, Lm


def test_landmark_indices() -> None:
    """Verify landmark indices 0 through 20 match MediaPipe 21-point hand model."""
    assert Lm.WRIST == 0
    assert Lm.THUMB_CMC == 1
    assert Lm.THUMB_MCP == 2
    assert Lm.THUMB_IP == 3
    assert Lm.THUMB_TIP == 4

    assert Lm.INDEX_FINGER_MCP == 5
    assert Lm.INDEX_FINGER_PIP == 6
    assert Lm.INDEX_FINGER_DIP == 7
    assert Lm.INDEX_FINGER_TIP == 8

    assert Lm.MIDDLE_FINGER_MCP == 9
    assert Lm.MIDDLE_FINGER_PIP == 10
    assert Lm.MIDDLE_FINGER_DIP == 11
    assert Lm.MIDDLE_FINGER_TIP == 12

    assert Lm.RING_FINGER_MCP == 13
    assert Lm.RING_FINGER_PIP == 14
    assert Lm.RING_FINGER_DIP == 15
    assert Lm.RING_FINGER_TIP == 16

    assert Lm.PINKY_MCP == 17
    assert Lm.PINKY_PIP == 18
    assert Lm.PINKY_DIP == 19
    assert Lm.PINKY_TIP == 20

    assert len(Lm) == 21


def test_finger_chains() -> None:
    """Verify 5 finger chains are defined with 4 landmarks each."""
    assert set(FINGER_CHAINS.keys()) == {"thumb", "index", "middle", "ring", "pinky"}
    for _name, chain in FINGER_CHAINS.items():
        assert len(chain) == 4
        assert all(isinstance(lm, Lm) for lm in chain)


def test_hand_connections() -> None:
    """Verify hand skeleton connections comprise valid landmark pairs."""
    assert len(HAND_CONNECTIONS) > 15
    for start_lm, end_lm in HAND_CONNECTIONS:
        assert isinstance(start_lm, Lm)
        assert isinstance(end_lm, Lm)
        assert start_lm != end_lm
