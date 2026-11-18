"""Unit tests for JSONL landmark recording and replaying."""

from pathlib import Path

import numpy as np

from aileron.interfaces import Hand, HandFrame, Side
from aileron.replay import ReplayReader, ReplayWriter


def test_replay_roundtrip(tmp_path: Path) -> None:
    """Verify writing and reading HandFrame produces identical landmarks."""
    replay_file = tmp_path / "test_stream.jsonl"

    lm1 = np.ones((21, 3), dtype=np.float32) * 0.5
    world1 = np.zeros((21, 3), dtype=np.float32)
    h1 = Hand(side=Side.RIGHT, score=0.95, lm=lm1, world=world1)
    frame1 = HandFrame(t_capture_ns=1000, t_infer_done_ns=1000, seq=1, hands=(h1,))

    with ReplayWriter(replay_file, fps_nominal=60, notes="unit test") as writer:
        writer.write_frame(frame1)
        writer.write_expect(t_ns=1000, event="CLICK_LEFT")

    reader = ReplayReader(replay_file)
    assert reader.header.get("app") == "aileron"
    assert reader.header.get("fps_nominal") == 60

    frames, expects = reader.load_all()
    assert len(frames) == 1
    assert len(expects) == 1

    loaded_frame = frames[0]
    assert loaded_frame.seq == 1
    assert loaded_frame.t_capture_ns == 1000
    assert len(loaded_frame.hands) == 1

    loaded_hand = loaded_frame.hands[0]
    assert loaded_hand.side == Side.RIGHT
    assert abs(loaded_hand.score - 0.95) < 1e-3
    assert np.allclose(loaded_hand.lm, lm1, atol=1e-4)
    assert np.allclose(loaded_hand.world, world1, atol=1e-4)

    assert expects[0]["event"] == "CLICK_LEFT"
