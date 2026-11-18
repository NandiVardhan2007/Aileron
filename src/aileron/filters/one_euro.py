"""One Euro adaptive low-pass filter for low-jitter, low-latency signal smoothing."""

import math

from aileron.config import OneEuroConfig

# Clamping bounds for delta time Te per SIGNAL_PROCESSING.md §12
TE_MIN_SEC = 0.001  # 1 ms
TE_MAX_SEC = 0.100  # 100 ms


class OneEuroFilter1D:
    """1D One Euro filter implementation adhering to Filter1D protocol."""

    def __init__(self, min_cutoff: float = 1.2, beta: float = 8.0, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)

        self._x_prev: float | None = None
        self._dx_prev: float = 0.0
        self._t_prev_ns: int | None = None

    @classmethod
    def from_config(cls, cfg: OneEuroConfig) -> "OneEuroFilter1D":
        """Instantiate from a Pydantic OneEuroConfig model."""
        return cls(min_cutoff=cfg.min_cutoff, beta=cfg.beta, d_cutoff=cfg.d_cutoff)

    def _alpha(self, cutoff: float, te: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(1e-4, cutoff))
        return 1.0 / (1.0 + tau / max(1e-4, te))

    def __call__(self, x: float, t_ns: int) -> float:
        """Filter value x given timestamp in nanoseconds."""
        if self._x_prev is None or self._t_prev_ns is None:
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev_ns = t_ns
            return x

        raw_te = (t_ns - self._t_prev_ns) / 1_000_000_000.0
        te = max(TE_MIN_SEC, min(TE_MAX_SEC, raw_te))

        dx = (x - self._x_prev) / te
        alpha_d = self._alpha(self.d_cutoff, te)
        dx_hat = alpha_d * dx + (1.0 - alpha_d) * self._dx_prev

        fc = self.min_cutoff + self.beta * abs(dx_hat)
        alpha_x = self._alpha(fc, te)
        x_hat = alpha_x * x + (1.0 - alpha_x) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev_ns = t_ns

        return x_hat

    def reset(self) -> None:
        """Reset internal filter state on hand loss or mode change."""
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev_ns = None


class OneEuroFilter2D:
    """Pair of 1D One Euro filters for 2D coordinates (e.g. cursor, anchor)."""

    def __init__(self, min_cutoff: float = 1.2, beta: float = 8.0, d_cutoff: float = 1.0) -> None:
        self.fx = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
        self.fy = OneEuroFilter1D(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)

    @classmethod
    def from_config(cls, cfg: OneEuroConfig) -> "OneEuroFilter2D":
        return cls(min_cutoff=cfg.min_cutoff, beta=cfg.beta, d_cutoff=cfg.d_cutoff)

    def __call__(self, x: float, y: float, t_ns: int) -> tuple[float, float]:
        return self.fx(x, t_ns), self.fy(y, t_ns)

    def reset(self) -> None:
        self.fx.reset()
        self.fy.reset()
