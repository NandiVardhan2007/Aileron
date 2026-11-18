"""JSONL landmark recording and replaying utilities (PRIV-02: landmarks only, no video)."""

import json
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType

import numpy as np

from aileron.interfaces import Hand, HandFrame, Side


class ReplayWriter:
    """Serializes landmark streams into compliant JSONL format without persisting video."""

    def __init__(
        self,
        filepath: Path | str,
        fps_nominal: int = 60,
        mirrored: bool = True,
        notes: str = "",
    ) -> None:
        self.path = Path(filepath)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8")
        header = {
            "type": "header",
            "schema": 1,
            "app": "aileron",
            "fps_nominal": fps_nominal,
            "mirrored": mirrored,
            "notes": notes,
        }
        self._file.write(json.dumps(header) + "\n")
        self._file.flush()

    def write_frame(self, hand_frame: HandFrame) -> None:
        """Write a HandFrame entry."""
        hands_data = []
        for h in hand_frame.hands:
            hands_data.append(
                {
                    "side": h.side.value,
                    "score": round(float(h.score), 4),
                    "lm": [[round(float(v), 5) for v in row] for row in h.lm.tolist()],
                    "world": [[round(float(v), 5) for v in row] for row in h.world.tolist()],
                }
            )

        entry = {
            "type": "frame",
            "t_ns": hand_frame.t_capture_ns,
            "seq": hand_frame.seq,
            "hands": hands_data,
        }
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def write_expect(self, t_ns: int, event: str, **kwargs: object) -> None:
        """Write a test assertion expectation entry."""
        entry: dict[str, object] = {"type": "expect", "t_ns": t_ns, "event": event}
        entry.update(kwargs)
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def close(self) -> None:
        """Close the output file."""
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "ReplayWriter":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


class ReplayReader:
    """Reads and parses JSONL landmark stream replay files."""

    def __init__(self, filepath: Path | str) -> None:
        self.path = Path(filepath)
        if not self.path.is_file():
            raise FileNotFoundError(f"Replay file not found: {self.path}")

        self.header: dict[str, object] = {}
        with self.path.open(encoding="utf-8") as f:
            first_line = f.readline()
            if first_line:
                data = json.loads(first_line)
                if data.get("type") == "header":
                    self.header = data

    def iter_entries(self) -> Iterator[dict[str, object]]:
        """Iterate raw JSON objects skipping the header."""
        with self.path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if data.get("type") == "header":
                    continue
                yield data

    def load_all(self) -> tuple[list[HandFrame], list[dict[str, object]]]:
        """Load all HandFrames and expect assertions."""
        frames: list[HandFrame] = []
        expects: list[dict[str, object]] = []

        for item in self.iter_entries():
            kind = item.get("type")
            if kind == "frame":
                hands = []
                hands_list = item.get("hands", [])
                if isinstance(hands_list, list):
                    for h in hands_list:
                        hands.append(
                            Hand(
                                side=Side(str(h["side"])),
                                score=float(h["score"]),
                                lm=np.array(h["lm"], dtype=np.float32),
                                world=np.array(h["world"], dtype=np.float32),
                            )
                        )
                raw_t = item.get("t_ns", 0)
                t_capture = int(raw_t) if isinstance(raw_t, (int, float, str)) else 0
                raw_seq = item.get("seq", 0)
                seq_num = int(raw_seq) if isinstance(raw_seq, (int, float, str)) else 0
                frames.append(
                    HandFrame(
                        t_capture_ns=t_capture,
                        t_infer_done_ns=t_capture,
                        seq=seq_num,
                        hands=tuple(hands),
                    )
                )
            elif kind == "expect":
                expects.append(item)

        return frames, expects
