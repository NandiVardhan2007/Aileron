"""Replay fixture integration tests for pinch clicks, drags, double click, and right click."""

from pathlib import Path

from aileron.config import load_config
from aileron.features.extraction import extract_features
from aileron.gestures.engine import GestureEngine
from aileron.interfaces import GestureKind
from aileron.replay import ReplayReader


def test_replay_pinch_click() -> None:
    """Verify pinch_click.jsonl fixture emits CLICK_LEFT event."""
    fixture_path = Path("tests/replay/pinch_click.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)

    assert GestureKind.CLICK_LEFT in emitted_kinds
    assert GestureKind.DRAG_START not in emitted_kinds


def test_replay_pinch_drag() -> None:
    """Verify pinch_drag.jsonl fixture emits DRAG_START and DRAG_END."""
    fixture_path = Path("tests/replay/pinch_drag.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)

    assert GestureKind.DRAG_START in emitted_kinds
    assert GestureKind.DRAG_END in emitted_kinds


def test_replay_double_click() -> None:
    """Verify double_click.jsonl fixture emits DOUBLE_CLICK."""
    fixture_path = Path("tests/replay/double_click.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)

    assert GestureKind.DOUBLE_CLICK in emitted_kinds


def test_replay_right_click_vs_left() -> None:
    """Verify right_click_vs_left.jsonl fixture emits CLICK_RIGHT."""
    fixture_path = Path("tests/replay/right_click_vs_left.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)

    assert GestureKind.CLICK_RIGHT in emitted_kinds
    assert GestureKind.CLICK_LEFT not in emitted_kinds
