"""Unit tests for NullBackend ledger and intent recording."""

from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    ButtonUp,
    Key,
    MoveTo,
    Trigger,
)
from aileron.output.null import NullBackend


def test_null_backend_lifecycle() -> None:
    backend = NullBackend()
    assert not backend.is_open
    backend.open()
    assert backend.is_open

    backend.apply([MoveTo(x=100, y=200)])
    assert backend.cursor_pos == (100, 200)

    backend.apply([ButtonDown(button=Button.LEFT)])
    assert "button:left" in backend.held()

    backend.apply([ButtonUp(button=Button.LEFT)])
    assert "button:left" not in backend.held()

    backend.apply([Key(chord="ctrl", down=True)])
    assert "key:ctrl" in backend.held()

    backend.apply([Axis(name="lx", value=0.75)])
    assert "axis:lx" in backend.held()

    backend.apply([Trigger(name="rt", value=0.5)])
    assert "trigger:rt" in backend.held()

    # release_all must clear all held states
    backend.release_all()
    assert len(backend.held()) == 0

    backend.close()
    assert not backend.is_open
