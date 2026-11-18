"""Replay fixture integration tests for M3: scroll, zoom, and clutch/resume."""

from pathlib import Path

from aileron.config import load_config
from aileron.features.extraction import extract_features
from aileron.gestures.engine import GestureEngine
from aileron.interfaces import GestureKind
from aileron.replay import ReplayReader


def test_replay_scroll_vsign() -> None:
    """Verify scroll_vsign.jsonl fixture emits SCROLL_START event and scroll rate."""
    fixture_path = Path("tests/replay/scroll_vsign.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    max_scroll_y = 0.0

    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)
        if output.signals.scroll_rate[1] != 0.0:
            max_scroll_y = max(max_scroll_y, abs(output.signals.scroll_rate[1]))

    assert GestureKind.SCROLL_START in emitted_kinds
    assert max_scroll_y > 0.0


def test_replay_zoom_two_hand() -> None:
    """Verify zoom_two_hand.jsonl fixture emits ZOOM_START and zoom steps."""
    fixture_path = Path("tests/replay/zoom_two_hand.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    engine = GestureEngine(config)
    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []
    zoom_steps_total = 0

    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)
        zoom_steps_total += int(output.signals.zoom_delta)

    assert GestureKind.ZOOM_START in emitted_kinds
    assert zoom_steps_total > 0


def test_replay_clutch_resume() -> None:
    """Verify clutch_resume.jsonl fixture emits CLUTCH and RESUME dwell events."""
    fixture_path = Path("tests/replay/clutch_resume.jsonl")
    assert fixture_path.is_file()

    config = load_config()
    # Start engine in armed mode so clutch dwell can trigger
    engine = GestureEngine(config)
    engine.session_manager.trigger_resume()  # Armed

    reader = ReplayReader(fixture_path)
    frames, _ = reader.load_all()

    emitted_kinds: list[GestureKind] = []

    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        output, _intents = engine.process(frame, feats)
        for ev in output.events:
            emitted_kinds.append(ev.kind)

    assert GestureKind.CLUTCH in emitted_kinds
    assert GestureKind.RESUME in emitted_kinds
