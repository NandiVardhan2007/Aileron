"""Base abstractions and protocols for Aileron output backends."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from aileron.interfaces import Intent


@runtime_checkable
class OutputBackend(Protocol):
    """Protocol implemented by all platform and mock output backends."""

    name: str
    capabilities: frozenset[str]  # e.g. {"mouse", "keyboard", "gamepad"}

    def open(self) -> None:
        """Initialize the backend hardware/OS handle."""
        ...

    def close(self) -> None:
        """Shut down backend and guarantee release_all() is called."""
        ...

    def apply(self, intents: Sequence[Intent]) -> None:
        """Apply a sequence of approved intents to the OS/driver."""
        ...

    def release_all(self) -> None:
        """Release all currently held buttons, keys, axes, and triggers.

        Must be idempotent, must never raise an exception, and must complete in <1 ms.
        """
        ...

    def held(self) -> frozenset[str]:
        """Return the set of identifiers currently held down or active.

        Used by the safety ledger and test assertions.
        """
        ...
