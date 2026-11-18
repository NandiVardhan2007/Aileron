"""Held input tracking ledger to guarantee no stuck keys or mouse buttons (SAFE-03)."""

import threading

from aileron.interfaces import (
    Axis,
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    Intent,
    Key,
    Pad,
    PadButton,
    ReleaseAll,
    Trigger,
)

ZERO_THRESHOLD = 1e-4


class HeldInputLedger:
    """Thread-safe ledger tracking all currently active/pressed physical inputs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buttons: set[Button] = set()
        self._keys: set[str] = set()
        self._pads: set[PadButton] = set()
        self._axes: set[str] = set()
        self._triggers: set[str] = set()

    def _record_pointer_or_key(self, intent: Intent) -> None:
        match intent:
            case ButtonDown(button=btn):
                self._buttons.add(btn)
            case ButtonUp(button=btn):
                self._buttons.discard(btn)
            case Click():
                pass
            case Key(chord=chord, down=True):
                self._keys.add(chord)
            case Key(chord=chord, down=False):
                self._keys.discard(chord)
            case _:
                pass

    def _record_gamepad(self, intent: Intent) -> None:
        match intent:
            case Pad(button=btn, down=True):
                self._pads.add(btn)
            case Pad(button=btn, down=False):
                self._pads.discard(btn)
            case Axis(name=name, value=val):
                if abs(val) > ZERO_THRESHOLD:
                    self._axes.add(name)
                else:
                    self._axes.discard(name)
            case Trigger(name=name, value=val):
                if val > ZERO_THRESHOLD:
                    self._triggers.add(name)
                else:
                    self._triggers.discard(name)
            case ReleaseAll():
                self._clear_all()
            case _:
                pass

    def _clear_all(self) -> None:
        self._buttons.clear()
        self._keys.clear()
        self._pads.clear()
        self._axes.clear()
        self._triggers.clear()

    def record(self, intent: Intent) -> None:
        """Update ledger state based on an emitted intent."""
        with self._lock:
            if isinstance(intent, ButtonDown | ButtonUp | Click | Key):
                self._record_pointer_or_key(intent)
            else:
                self._record_gamepad(intent)

    def drain_and_create_releases(self) -> list[Intent]:
        """Generate compensatory release intents for all held states and clear ledger."""
        with self._lock:
            releases: list[Intent] = []
            for btn in self._buttons:
                releases.append(ButtonUp(button=btn))
            for key in self._keys:
                releases.append(Key(chord=key, down=False))
            for pad_btn in self._pads:
                releases.append(Pad(button=pad_btn, down=False))
            for axis in self._axes:
                releases.append(Axis(name=axis, value=0.0))  # type: ignore[arg-type]
            for trig in self._triggers:
                releases.append(Trigger(name=trig, value=0.0))  # type: ignore[arg-type]

            releases.append(ReleaseAll())
            self._clear_all()
            return releases

    def held(self) -> frozenset[str]:
        """Return human-readable set of currently held inputs for auditing."""
        with self._lock:
            res: set[str] = set()
            for b in self._buttons:
                res.add(f"button:{b.value}")
            for k in self._keys:
                res.add(f"key:{k}")
            for p in self._pads:
                res.add(f"pad:{p.value}")
            for a in self._axes:
                res.add(f"axis:{a}")
            for t in self._triggers:
                res.add(f"trigger:{t}")
            return frozenset(res)

    def is_empty(self) -> bool:
        """True if no inputs are currently held."""
        with self._lock:
            return not (self._buttons or self._keys or self._pads or self._axes or self._triggers)
