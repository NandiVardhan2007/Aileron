"""Replay integration tests for Cockpit mode Yoke profile (M5).

Verifies:
- yoke_turns.jsonl: Steering wheel angles and axis deflection
- trigger_ramp.jsonl: Progressive throttle trigger ramping
"""

import numpy as np

from aileron.config import AileronConfig, CockpitConfig
from aileron.features.extraction import extract_features
from aileron.interfaces import Axis, Hand, Side, Trigger
from aileron.landmarks import Lm
from aileron.modes.yoke import YokeProfile
from aileron.replay import ReplayReader


def test_replay_yoke_turns() -> None:
    """Verify yoke_turns replay produces steering axis deflections."""
    config = AileronConfig()
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0)
    yoke = YokeProfile(cockpit_cfg=c_cfg)
    yoke._axes_live = True

    reader = ReplayReader("tests/replay/yoke_turns.jsonl")
    frames, _ = reader.load_all()

    steer_values: list[float] = []

    for frame in frames:
        feats = [extract_features(h, config.tracking, config.fingers) for h in frame.hands]
        intents = yoke.process(frame.hands, feats, frame.t_capture_ns)
        for i in intents:
            if isinstance(i, Axis) and i.name == "lx":
                steer_values.append(i.value)

    assert len(steer_values) > 0
    # Both clockwise and counterclockwise turns should occur
    assert any(v > 0.1 for v in steer_values)
    assert any(v < -0.1 for v in steer_values)


def test_replay_trigger_ramp() -> None:
    """Verify trigger_ramp replay produces increasing throttle trigger values."""
    config = AileronConfig()
    c_cfg = CockpitConfig(neutral_hold_ms=100, ramp_in_ms=0)
    yoke = YokeProfile(cockpit_cfg=c_cfg)
    yoke._axes_live = True

    dummy_left = Hand(
        side=Side.LEFT,
        score=0.95,
        lm=np.zeros((21, 3), dtype=np.float32),
        world=np.zeros((21, 3), dtype=np.float32),
    )
    dummy_left.lm[int(Lm.MIDDLE_FINGER_MCP)] = [0.3, 0.5, 0.0]
    dummy_left_feat = extract_features(dummy_left, config.tracking, config.fingers)

    reader = ReplayReader("tests/replay/trigger_ramp.jsonl")
    frames, _ = reader.load_all()

    throttle_values: list[float] = []

    for frame in frames:
        if not frame.hands:
            continue
        right_h = frame.hands[0]
        right_f = extract_features(right_h, config.tracking, config.fingers)
        intents = yoke.process(
            (dummy_left, right_h),
            (dummy_left_feat, right_f),
            frame.t_capture_ns,
        )
        for i in intents:
            if isinstance(i, Trigger) and i.name == "rt":
                throttle_values.append(i.value)

    assert len(throttle_values) > 0
    # Values should start near 0 and ramp up
    assert throttle_values[0] < 0.2
    assert max(throttle_values) > 0.4
