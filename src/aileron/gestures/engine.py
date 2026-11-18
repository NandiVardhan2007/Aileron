"""Gesture engine orchestrating detectors, primary-hand tracking, and intent generation."""

from collections.abc import Sequence
from typing import ClassVar

from aileron.config import AileronConfig
from aileron.filters.one_euro import OneEuroFilter2D
from aileron.gestures.dwell import DwellGestureDetector
from aileron.gestures.pinch import PinchGestureDetector
from aileron.gestures.scroll import ScrollDetector
from aileron.gestures.zoom import ZoomDetector
from aileron.interfaces import (
    Button,
    ButtonDown,
    ButtonUp,
    Click,
    GestureDetector,
    GestureEvent,
    GestureKind,
    GestureOutput,
    HandFeatures,
    HandFrame,
    Intent,
    ReleaseAll,
    Scroll,
    Side,
    Signals,
    Zoom,
)
from aileron.mapping.cursor import CursorMapper
from aileron.modes.manager import ModeManager
from aileron.modes.session import SessionStateManager
from aileron.safety.gate import SafetyGate


class PrimaryHandTracker:
    """Tracks sticky primary hand selection per SIG-11 and SIGNAL_PROCESSING §11."""

    def __init__(self, hand_lost_ms: int = 150, engage_ms: int = 300) -> None:
        self.hand_lost_ms = hand_lost_ms
        self.engage_ms = engage_ms
        self.locked_side: Side | None = None
        self._last_seen_ns: int = 0
        self._first_seen_ns: int = 0
        self._engaged: bool = False

    def reset(self) -> None:
        """Reset sticky hand lock and engagement state."""
        self.locked_side = None
        self._last_seen_ns = 0
        self._first_seen_ns = 0
        self._engaged = False

    def is_engaged(self, t_ns: int) -> bool:
        """True when hand has dwelt for engage_ms (G-01)."""
        if self.engage_ms <= 0:
            return True
        if self._first_seen_ns <= 0:
            return False
        return (t_ns - self._first_seen_ns) >= self.engage_ms * 1_000_000

    def select(
        self, feats: Sequence[HandFeatures], t_ns: int
    ) -> tuple[HandFeatures | None, Sequence[GestureEvent]]:
        """Select primary hand with sticky lock, timeout, and emit ENGAGED/DISENGAGED events."""
        events: list[GestureEvent] = []
        valid_feats = [f for f in feats if f.valid]

        if not valid_feats:
            if self.locked_side is not None:
                elapsed_ms = (t_ns - self._last_seen_ns) / 1_000_000.0
                if elapsed_ms > self.hand_lost_ms:
                    events.append(
                        GestureEvent(
                            kind=GestureKind.DISENGAGED,
                            t_ns=t_ns,
                            side=self.locked_side,
                        )
                    )
                    self.reset()
            return None, tuple(events)

        # If already locked, stick to that side if still present
        if self.locked_side is not None:
            for f in valid_feats:
                if f.side == self.locked_side:
                    self._last_seen_ns = t_ns
                    if not self._engaged and self.is_engaged(t_ns):
                        self._engaged = True
                        events.append(
                            GestureEvent(
                                kind=GestureKind.ENGAGED,
                                t_ns=t_ns,
                                side=self.locked_side,
                            )
                        )
                    return f, tuple(events)

            # Locked hand not in this frame; check timeout
            elapsed_ms = (t_ns - self._last_seen_ns) / 1_000_000.0
            if elapsed_ms > self.hand_lost_ms:
                events.append(
                    GestureEvent(
                        kind=GestureKind.DISENGAGED,
                        t_ns=t_ns,
                        side=self.locked_side,
                    )
                )
                self.reset()
            else:
                return None, tuple(events)

        # Select new primary hand: tie-break by largest palm size
        best_hand = max(valid_feats, key=lambda f: f.palm_size)
        self.locked_side = best_hand.side
        self._last_seen_ns = t_ns
        self._first_seen_ns = t_ns
        self._engaged = self.engage_ms <= 0
        if self._engaged:
            events.append(
                GestureEvent(
                    kind=GestureKind.ENGAGED,
                    t_ns=t_ns,
                    side=self.locked_side,
                )
            )

        return best_hand, tuple(events)


class GestureEngine:
    """Top-level gesture pipeline dispatcher for Pointer and Cockpit modes."""

    def __init__(
        self,
        config: AileronConfig,
        mapper: CursorMapper | None = None,
        custom_detectors: Sequence[GestureDetector] | None = None,
        safety_gate: SafetyGate | None = None,
        session_manager: SessionStateManager | None = None,
        mode_manager: ModeManager | None = None,
    ) -> None:
        self.config = config
        if mapper is not None:
            self.mapper = mapper
        else:
            filter_2d = OneEuroFilter2D(
                min_cutoff=config.filters.cursor.min_cutoff,
                beta=config.filters.cursor.beta,
                d_cutoff=config.filters.cursor.d_cutoff,
            )
            self.mapper = CursorMapper(config.pointer, filter_2d=filter_2d)

        self.hand_tracker = PrimaryHandTracker(
            config.tracking.hand_lost_ms,
            config.tracking.engage_ms,
        )

        gate = safety_gate or SafetyGate()
        self.session_manager = session_manager or SessionStateManager(
            gate, start_armed=config.session.start_armed
        )
        self.mode_manager = mode_manager or ModeManager(config.cockpit)

        self.pinch_detector = PinchGestureDetector(config.click)
        self.scroll_detector = ScrollDetector(config.scroll, config.fingers)
        self.zoom_detector = ZoomDetector(config.zoom, config.click)
        self.dwell_detector = DwellGestureDetector(
            config.session,
            config.fingers,
            config.tracking,
        )

        self.custom_detectors = list(custom_detectors) if custom_detectors else []

    def reset(self) -> None:
        """Reset all internal detectors and state."""
        self.hand_tracker.reset()
        self.mapper.reset()
        self.pinch_detector.reset()
        self.scroll_detector.reset()
        self.zoom_detector.reset()
        self.dwell_detector.reset()
        for d in self.custom_detectors:
            d.reset()

    def process(
        self,
        hand_frame: HandFrame,
        features: Sequence[HandFeatures],
    ) -> tuple[GestureOutput, tuple[Intent, ...]]:
        """Process one frame of hand features, emitting gesture events and output intents."""
        t_ns = hand_frame.t_capture_ns

        # 1. Primary hand selection
        primary_hand, hand_events = self.hand_tracker.select(features, t_ns)
        primary_seq: tuple[HandFeatures, ...] = (primary_hand,) if primary_hand is not None else ()

        # 2. Run detectors
        events: list[GestureEvent] = list(hand_events)
        events.extend(self.pinch_detector.update(primary_seq, t_ns))
        events.extend(self.scroll_detector.update(primary_seq, t_ns))
        events.extend(self.zoom_detector.update(features, t_ns))
        events.extend(
            self.dwell_detector.update_with_state(primary_seq, t_ns, self.session_manager.state)
        )
        for cd in self.custom_detectors:
            events.extend(cd.update(primary_seq, t_ns))

        # 3. Update cursor freeze based on pinch and scroll states
        is_frozen = self.pinch_detector.is_cursor_frozen or self.scroll_detector.is_cursor_frozen
        self.mapper.set_click_freeze(is_frozen)

        # 4. Map continuous cursor motion (if engaged)
        intents: list[Intent] = []
        cursor_signal: tuple[float, float] | None = None

        if primary_hand is not None:
            cursor_signal = primary_hand.anchor
            if self.hand_tracker.is_engaged(t_ns):
                move_intent = self.mapper.map_anchor(primary_hand.anchor, t_ns)
                if move_intent is not None:
                    intents.append(move_intent)
        else:
            self.mapper.reset()

        # 5. Incremental scroll & zoom intents
        if self.scroll_detector.lines_delta != (0.0, 0.0):
            intents.append(
                Scroll(
                    dx=self.scroll_detector.lines_delta[0],
                    dy=self.scroll_detector.lines_delta[1],
                )
            )

        if self.zoom_detector.zoom_steps_delta != 0:
            intents.append(Zoom(steps=self.zoom_detector.zoom_steps_delta))

        # 6. Translate discrete gesture events to intents and trigger state transitions
        intents.extend(self._dispatch_events(events))

        # 7. Form GestureOutput and return
        signals = Signals(
            cursor=cursor_signal,
            scroll_rate=self.scroll_detector.scroll_rate,
            zoom_delta=float(self.zoom_detector.zoom_steps_delta),
            dwell_progress=self.dwell_detector.progress_dict or None,
        )
        gesture_output = GestureOutput(t_ns=t_ns, events=tuple(events), signals=signals)

        return gesture_output, tuple(intents)

    def _dispatch_events(self, events: Sequence[GestureEvent]) -> list[Intent]:
        """Dispatch events to session/mode managers or map directly to intents."""
        out: list[Intent] = []
        for ev in events:
            if ev.kind == GestureKind.CLUTCH:
                out.extend(self.session_manager.trigger_clutch())
            elif ev.kind == GestureKind.RESUME:
                out.extend(self.session_manager.trigger_resume())
            elif ev.kind == GestureKind.MODE_TOGGLE:
                _, releases = self.mode_manager.toggle_mode()
                out.extend(releases)
            elif ev.kind == GestureKind.DISENGAGED:
                out.append(ReleaseAll())
            else:
                translated = self._translate_event_to_intent(ev)
                if translated is not None:
                    out.append(translated)
        return out

    _INTENT_MAP: ClassVar[dict[GestureKind, Intent]] = {
        GestureKind.CLICK_LEFT: Click(button=Button.LEFT, count=1),
        GestureKind.DOUBLE_CLICK: Click(button=Button.LEFT, count=2),
        GestureKind.CLICK_RIGHT: Click(button=Button.RIGHT, count=1),
        GestureKind.CLICK_MIDDLE: Click(button=Button.MIDDLE, count=1),
        GestureKind.DRAG_START: ButtonDown(button=Button.LEFT),
        GestureKind.DRAG_END: ButtonUp(button=Button.LEFT),
    }

    def _translate_event_to_intent(self, ev: GestureEvent) -> Intent | None:
        """Map discrete GestureEvent to an output Intent."""
        return self._INTENT_MAP.get(ev.kind)
