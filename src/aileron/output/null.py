"""NullBackend for safe automated runs, testing, and simulation."""

import threading
from collections.abc import Sequence

from aileron.interfaces import (
    Axis,
    ButtonDown,
    ButtonUp,
    Click,
    Intent,
    Key,
    MoveBy,
    MoveTo,
    Pad,
    ReleaseAll,
    Scroll,
    Trigger,
    Zoom,
)

ZERO_THRESHOLD = 1e-4


class NullBackend:
    """Safe no-op output backend that records intents and manages a held ledger."""

    name: str = "null"
    capabilities: frozenset[str] = frozenset({"mouse", "keyboard", "gamepad"})

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._is_open: bool = False
        self._recorded_intents: list[Intent] = []
        self._held_items: set[str] = set()
        self.cursor_pos: tuple[int, int] = (0, 0)

    @property
    def is_open(self) -> bool:
        """Check if backend is open."""
        return self._is_open

    @property
    def recorded_intents(self) -> list[Intent]:
        """List of intents recorded since creation or last clear."""
        with self._lock:
            return list(self._recorded_intents)

    def clear(self) -> None:
        """Clear recorded intents."""
        with self._lock:
            self._recorded_intents.clear()

    def open(self) -> None:
        """Open the backend."""
        with self._lock:
            self._is_open = True

    def close(self) -> None:
        """Close backend and release all held inputs."""
        self.release_all()
        with self._lock:
            self._is_open = False

    def release_all(self) -> None:
        """Release all held inputs idempotently without raising."""
        with self._lock:
            self._held_items.clear()
            self._recorded_intents.append(ReleaseAll())

    def held(self) -> frozenset[str]:
        """Return the current set of held inputs."""
        with self._lock:
            return frozenset(self._held_items)

    def _apply_pointer_intent(self, intent: Intent) -> None:
        match intent:
            case MoveTo(x=x, y=y):
                self.cursor_pos = (x, y)
            case MoveBy(dx=dx, dy=dy):
                self.cursor_pos = (self.cursor_pos[0] + dx, self.cursor_pos[1] + dy)
            case ButtonDown(button=btn):
                self._held_items.add(f"button:{btn.value}")
            case ButtonUp(button=btn):
                self._held_items.discard(f"button:{btn.value}")
            case Click() | Scroll() | Zoom():
                pass
            case _:
                pass

    def _apply_gamepad_or_key_intent(self, intent: Intent) -> None:
        match intent:
            case Key(chord=chord, down=True):
                self._held_items.add(f"key:{chord}")
            case Key(chord=chord, down=False):
                self._held_items.discard(f"key:{chord}")
            case Pad(button=btn, down=True):
                self._held_items.add(f"pad:{btn.value}")
            case Pad(button=btn, down=False):
                self._held_items.discard(f"pad:{btn.value}")
            case Axis(name=name, value=val):
                if abs(val) > ZERO_THRESHOLD:
                    self._held_items.add(f"axis:{name}")
                else:
                    self._held_items.discard(f"axis:{name}")
            case Trigger(name=name, value=val):
                if val > ZERO_THRESHOLD:
                    self._held_items.add(f"trigger:{name}")
                else:
                    self._held_items.discard(f"trigger:{name}")
            case ReleaseAll():
                self._held_items.clear()
            case _:
                pass

    def apply(self, intents: Sequence[Intent]) -> None:
        """Apply intents and update held state."""
        with self._lock:
            for intent in intents:
                self._recorded_intents.append(intent)
                if isinstance(
                    intent, MoveTo | MoveBy | ButtonDown | ButtonUp | Click | Scroll | Zoom
                ):
                    self._apply_pointer_intent(intent)
                else:
                    self._apply_gamepad_or_key_intent(intent)
