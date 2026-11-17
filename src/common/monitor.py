"""Synthetic display samples, independent of test criteria and hardware I/O."""
import math
from dataclasses import dataclass

from src.common.testing import Sample

DEFAULT_MONITOR_CHANNELS = (
    {'id': 'analog_a', 'label': 'Analog A', 'kind': 'analog', 'unit': 'V'},
    {'id': 'analog_b', 'label': 'Analog B', 'kind': 'analog', 'unit': 'V'},
    {'id': 'pwm_1', 'label': 'PWM 1', 'kind': 'pwm', 'unit': 'V'},
    {'id': 'pwm_2', 'label': 'PWM 2', 'kind': 'pwm', 'unit': 'V'},
)


@dataclass(frozen=True)
class PwmPreview:
    frequency_hz: float
    duty_percent: float
    points: tuple
    window_ms: float
    low: float = 0.0
    high: float = 5.0


def demo_pwm_frame(frequency_hz, duty_percent):
    """Four synthetic cycles with explicit vertical edges; never hardware data."""
    if not math.isfinite(frequency_hz) or frequency_hz <= 0 or not 0 < duty_percent < 100:
        raise ValueError('Invalid demo PWM frequency/duty')
    period_ms = 1000 / frequency_hz
    on_ms = period_ms * duty_percent / 100
    points = []
    for cycle in range(4):
        start = cycle * period_ms
        points.extend(((start, 0.0), (start, 5.0), (start + on_ms, 5.0),
                       (start + on_ms, 0.0), ((cycle + 1) * period_ms, 0.0)))
    return PwmPreview(frequency_hz, duty_percent, tuple(points), 4 * period_ms)


def demo_monitor_samples(channels, elapsed, timestamp):
    samples = {}
    for index, channel in enumerate(channels):
        phase = elapsed * .8 + index
        if channel['kind'] == 'analog':
            value = 2.5 + .35 * math.sin(phase) + .04 * math.sin(phase * 4)
        else:
            value = demo_pwm_frame(800 + index * 100, 45 + 15 * math.sin(phase * .3))
        samples[channel['id']] = Sample(value, timestamp, 'valid', 'monitor_demo')
    return samples
