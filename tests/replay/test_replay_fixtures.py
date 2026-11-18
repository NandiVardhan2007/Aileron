"""Tests verifying that all synthesized replay fixtures load and validate."""

from pathlib import Path

from aileron.replay import ReplayReader


def test_all_fixtures_loadable() -> None:
    replay_dir = Path("tests/replay")
    assert replay_dir.is_dir()

    fixture_files = list(replay_dir.glob("*.jsonl"))
    assert len(fixture_files) >= 15

    for fpath in fixture_files:
        reader = ReplayReader(fpath)
        assert reader.header.get("app") == "aileron"
        frames, _expects = reader.load_all()
        assert len(frames) > 0
        for frame in frames:
            assert frame.t_capture_ns >= 0
            for hand in frame.hands:
                assert hand.lm.shape == (21, 3)
                assert hand.world.shape == (21, 3)
