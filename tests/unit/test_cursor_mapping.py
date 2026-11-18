"""Unit tests for active-region cursor mapping and bounds clamping."""

from aileron.config import PointerConfig
from aileron.interfaces import MoveBy, MoveTo
from aileron.mapping.cursor import CursorMapper, DesktopBounds, apply_gamma


def test_gamma_curve() -> None:
    """Verify gamma curve leaves center unchanged and is monotonic."""
    assert abs(apply_gamma(0.5, gamma=1.5) - 0.5) < 1e-4
    assert abs(apply_gamma(0.0, gamma=1.5) - 0.0) < 1e-4
    assert abs(apply_gamma(1.0, gamma=1.5) - 1.0) < 1e-4

    # Monotonicity
    prev = -1.0
    for i in range(11):
        val = apply_gamma(i / 10.0, gamma=1.5)
        assert val >= prev
        prev = val


def test_absolute_mapping_center_and_clamping() -> None:
    """Verify mapping active region center maps to virtual desktop center."""
    cfg = PointerConfig(
        mode="absolute",
        region_w=0.6,
        region_h=0.5,
        region_cx=0.5,
        region_cy=0.5,
        min_move_px=0,
    )
    bounds = DesktopBounds(vx=0, vy=0, vw=1920, vh=1080)
    mapper = CursorMapper(config=cfg, desktop_bounds=bounds)

    # Center of active region (0.5, 0.5)
    intent = mapper.map_anchor((0.5, 0.5), t_ns=1000)
    assert isinstance(intent, MoveTo)
    assert abs(intent.x - 960) <= 2
    assert abs(intent.y - 540) <= 2

    # Outside active region bounds -> clamps to desktop edges (SAFE-06)
    mapper.reset()
    intent_corner = mapper.map_anchor((0.0, 0.0), t_ns=2000)
    assert isinstance(intent_corner, MoveTo)
    assert intent_corner.x == 0
    assert intent_corner.y == 0

    mapper.reset()
    intent_far = mapper.map_anchor((1.0, 1.0), t_ns=3000)
    assert isinstance(intent_far, MoveTo)
    assert intent_far.x == 1919
    assert intent_far.y == 1079


def test_click_freeze() -> None:
    """Verify engaging click freeze holds cursor coordinates."""
    cfg = PointerConfig(
        mode="absolute",
        region_w=0.6,
        region_h=0.5,
        region_cx=0.5,
        region_cy=0.5,
        freeze_damping=1.0,
        min_move_px=0,
    )
    bounds = DesktopBounds(vx=0, vy=0, vw=1920, vh=1080)
    mapper = CursorMapper(config=cfg, desktop_bounds=bounds)

    # Initial move
    init_intent = mapper.map_anchor((0.5, 0.5), t_ns=1000)
    assert isinstance(init_intent, MoveTo)
    freeze_x, freeze_y = init_intent.x, init_intent.y

    mapper.set_click_freeze(True)

    # Hand moves slightly during pinch
    move_intent = mapper.map_anchor((0.52, 0.52), t_ns=2000)
    # Cursor should stay held at freeze position
    if move_intent is not None:
        assert isinstance(move_intent, MoveTo)
        assert move_intent.x == freeze_x
        assert move_intent.y == freeze_y


def test_relative_mapping() -> None:
    """Verify relative mode produces MoveBy intents."""
    cfg = PointerConfig(
        mode="relative",
        region_w=0.6,
        region_h=0.5,
        relative_gain=1000.0,
        min_move_px=0,
    )
    mapper = CursorMapper(config=cfg)

    # First point establishes reference
    res1 = mapper.map_anchor((0.5, 0.5), t_ns=1000)
    assert res1 is None

    # Second point produces relative delta
    res2 = mapper.map_anchor((0.55, 0.5), t_ns=2000)
    assert isinstance(res2, MoveBy)
    assert res2.dx > 0
    assert res2.dy == 0
