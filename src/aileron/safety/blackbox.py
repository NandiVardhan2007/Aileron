"""Black-box circular buffer for crash and safety fault investigation (M4).

Follows SAFETY §6 and PRIV-02:
- Retains only landmarks and emitted intents (no raw camera frames or pixel data).
- Circular ring buffer of the last N frames (~10 seconds at 60 FPS = 600 frames).
- Dumps to local JSONL file upon FAULT or explicit export request.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aileron.interfaces import HandFrame, Intent

DEFAULT_RING_CAPACITY = 600  # ~10s at 60 FPS


@dataclass(frozen=True, slots=True)
class BlackBoxRecord:
    """Single tick snapshot stored in the blackbox ring buffer."""

    t_ns: int
    frame_dict: dict[str, Any]
    intents_dict: list[dict[str, Any]]


class BlackBoxRecorder:
    """In-memory rolling black-box recorder storing landmark frames and intents."""

    def __init__(self, capacity: int = DEFAULT_RING_CAPACITY, enabled: bool = True) -> None:
        self.capacity = capacity
        self.enabled = enabled
        self._buffer: deque[BlackBoxRecord] = deque(maxlen=capacity)

    def record(self, frame: HandFrame, intents: Sequence[Intent]) -> None:
        """Record one frame and its associated intents into the circular buffer."""
        if not self.enabled:
            return

        frame_data: dict[str, Any] = {
            "t_capture_ns": frame.t_capture_ns,
            "seq": frame.seq,
            "hands": [
                {
                    "side": h.side.value,
                    "score": h.score,
                    "lm": h.lm.tolist(),
                    "world": h.world.tolist(),
                }
                for h in frame.hands
            ],
        }

        intents_data: list[dict[str, Any]] = [asdict(i) for i in intents]

        self._buffer.append(
            BlackBoxRecord(
                t_ns=frame.t_capture_ns,
                frame_dict=frame_data,
                intents_dict=intents_data,
            )
        )

    def clear(self) -> None:
        """Clear all stored records."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    def dump_to_file(self, target_path: str | Path, reason: str = "fault") -> Path:
        """Dump the ring buffer contents to a JSONL file."""
        path = Path(target_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        header = {
            "aileron_version": "0.1.0",
            "type": "blackbox_dump",
            "reason": reason,
            "records_count": len(self._buffer),
        }

        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            for rec in self._buffer:
                line = {
                    "t_ns": rec.t_ns,
                    "frame": rec.frame_dict,
                    "intents": rec.intents_dict,
                }
                f.write(json.dumps(line) + "\n")

        return path
