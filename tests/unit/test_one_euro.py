"""Unit tests for One Euro adaptive low-pass filter."""

import random

from aileron.filters.one_euro import OneEuroFilter1D, OneEuroFilter2D


def test_one_euro_filter_steady_noise_attenuation() -> None:
    """Verify filter significantly attenuates high-frequency jitter on stationary signal."""
    filt = OneEuroFilter1D(min_cutoff=1.0, beta=1.0, d_cutoff=1.0)
    dt_ns = 16_666_666  # ~60 FPS

    raw_values = []
    filtered_values = []

    random.seed(42)
    for i in range(200):
        t_ns = i * dt_ns
        noise = random.gauss(0, 0.05)
        val = 0.5 + noise
        raw_values.append(val)
        filtered_values.append(filt(val, t_ns))

    # Skip initial warm up
    raw_var = sum((x - 0.5) ** 2 for x in raw_values[50:]) / len(raw_values[50:])
    filt_var = sum((x - 0.5) ** 2 for x in filtered_values[50:]) / len(filtered_values[50:])

    # Filtered variance should be at least 3x lower than raw noise
    assert filt_var < raw_var / 3.0


def test_one_euro_step_response_tracking() -> None:
    """Verify filter tracks rapid step changes without lagging permanently."""
    filt = OneEuroFilter1D(min_cutoff=1.2, beta=10.0, d_cutoff=1.0)
    dt_ns = 16_666_666

    # Steady at 0.0
    for i in range(30):
        filt(0.0, i * dt_ns)

    # Step to 1.0
    final_val = 0.0
    for i in range(30, 40):
        final_val = filt(1.0, i * dt_ns)

    # Should converge close to 1.0 within 10 frames (~160 ms)
    assert final_val > 0.85


def test_one_euro_reset() -> None:
    """Verify reset clears state and accepts new values without smoothing from old state."""
    filt = OneEuroFilter1D(min_cutoff=1.0, beta=1.0)
    filt(0.0, 0)
    filt(0.0, 16_000_000)

    filt.reset()
    # Immediately returns new position without transitioning from 0.0
    val = filt(1.0, 32_000_000)
    assert val == 1.0


def test_one_euro_2d() -> None:
    """Verify 2D wrapper filters both channels."""
    f2d = OneEuroFilter2D(min_cutoff=1.2, beta=8.0)
    x, y = f2d(0.5, 0.5, 1000)
    assert x == 0.5
    assert y == 0.5
