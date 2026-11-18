"""Cursor active-region mapping, gamma curves, and virtual desktop projection."""

import math
from dataclasses import dataclass

from aileron.config import PointerConfig
from aileron.filters.one_euro import OneEuroFilter2D
from aileron.interfaces import Intent, MoveBy, MoveTo

GAMMA_EPSILON = 1e-4


@dataclass(frozen=True, slots=True)
class DesktopBounds:
    """Virtual desktop bounding box in physical pixels (multi-monitor aware)."""

    vx: int = 0
    vy: int = 0
    vw: int = 1920
    vh: int = 1080

    @classmethod
    def default(cls) -> "DesktopBounds":
        return cls(vx=0, vy=0, vw=1920, vh=1080)


def apply_gamma(val: float, gamma: float) -> float:
    """Apply edge/center non-linear gain curve around center (0.5)."""
    if abs(gamma - 1.0) < GAMMA_EPSILON:
        return val
    centered = val - 0.5
    sign = 1.0 if centered >= 0 else -1.0
    scaled = abs(2.0 * centered)
    return float(0.5 + sign * (scaled**gamma) / 2.0)


class CursorMapper:
    """Maps normalized hand anchor to virtual desktop physical coordinates."""

    def __init__(
        self,
        config: PointerConfig,
        desktop_bounds: DesktopBounds | None = None,
        filter_2d: OneEuroFilter2D | None = None,
    ) -> None:
        self.config = config
        self.bounds = desktop_bounds or DesktopBounds.default()
        self.filter = filter_2d or OneEuroFilter2D(min_cutoff=1.2, beta=8.0, d_cutoff=1.0)

        self._prev_pixel: tuple[int, int] | None = None
        self._prev_u_prime: float | None = None
        self._prev_v_prime: float | None = None
        self._freeze_pos: tuple[int, int] | None = None
        self._is_frozen: bool = False

    def reset(self) -> None:
        """Reset cursor filter and position history on hand loss or mode change."""
        self.filter.reset()
        self._prev_pixel = None
        self._prev_u_prime = None
        self._prev_v_prime = None
        self._freeze_pos = None
        self._is_frozen = False

    def set_click_freeze(self, frozen: bool) -> None:
        """Engage or disengage click freeze to protect targeting accuracy during clicks."""
        self._is_frozen = frozen
        if frozen and self._prev_pixel is not None:
            self._freeze_pos = self._prev_pixel
        elif not frozen:
            self._freeze_pos = None

    def map_anchor(
        self,
        anchor: tuple[float, float],
        t_ns: int,
    ) -> Intent | None:
        """Convert hand anchor (x, y) to a MoveTo or MoveBy intent."""
        # 1. Map anchor into normalized active region [0.0 .. 1.0]
        x0 = self.config.region_cx - self.config.region_w / 2.0
        y0 = self.config.region_cy - self.config.region_h / 2.0

        raw_u = (anchor[0] - x0) / max(1e-4, self.config.region_w)
        raw_v = (anchor[1] - y0) / max(1e-4, self.config.region_h)

        clamped_u = max(0.0, min(1.0, raw_u))
        clamped_v = max(0.0, min(1.0, raw_v))

        # 2. Filter u, v with One Euro
        filt_u, filt_v = self.filter(clamped_u, clamped_v, t_ns)

        # 3. Apply gamma gain curve
        u_prime = apply_gamma(filt_u, self.config.gamma)
        v_prime = apply_gamma(filt_v, self.config.gamma)

        # 4. Compute target pixels
        if self.config.mode == "absolute":
            px_x = round(self.bounds.vx + u_prime * self.bounds.vw)
            px_y = round(self.bounds.vy + v_prime * self.bounds.vh)

            # Apply click freeze if active (ADR-003, SIG-06)
            if self._is_frozen and self._freeze_pos is not None:
                damp = self.config.freeze_damping
                px_x = round(self._freeze_pos[0] * damp + px_x * (1.0 - damp))
                px_y = round(self._freeze_pos[1] * damp + px_y * (1.0 - damp))

            # Clamp to virtual desktop bounds (SAFE-06)
            clamped_x = max(self.bounds.vx, min(self.bounds.vx + self.bounds.vw - 1, px_x))
            clamped_y = max(self.bounds.vy, min(self.bounds.vy + self.bounds.vh - 1, px_y))

            # Check min move threshold
            if self._prev_pixel is not None:
                dx = clamped_x - self._prev_pixel[0]
                dy = clamped_y - self._prev_pixel[1]
                if math.hypot(dx, dy) < self.config.min_move_px:
                    return None

            self._prev_pixel = (clamped_x, clamped_y)
            return MoveTo(x=clamped_x, y=clamped_y)

        else:
            # Relative trackpad-like mode
            if self._prev_u_prime is None or self._prev_v_prime is None:
                self._prev_u_prime = u_prime
                self._prev_v_prime = v_prime
                return None

            du = u_prime - self._prev_u_prime
            dv = v_prime - self._prev_v_prime
            self._prev_u_prime = u_prime
            self._prev_v_prime = v_prime

            speed = math.hypot(du, dv)
            gain = self.config.relative_gain * (1.0 + self.config.accel * speed)

            dx = round(du * gain)
            dy = round(dv * gain)

            if self._is_frozen:
                damp = self.config.freeze_damping
                dx = round(dx * (1.0 - damp))
                dy = round(dy * (1.0 - damp))

            if math.hypot(dx, dy) < self.config.min_move_px:
                return None

            return MoveBy(dx=dx, dy=dy)
