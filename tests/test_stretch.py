"""Pitch shifting and time stretching (src/stretch.py, Rubber Band).

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.stretch import (pitch_shift, time_stretch, transform, read_at_rate,
                         steps_to_curve, parallel_map)
from src.mixer import _stretch_mix_by_tempo

SR = 22050


def _tone(f=440.0, dur=1.0, ch=None):
    t = np.arange(int(dur * SR)) / SR
    x = (0.3 * np.sin(2 * np.pi * f * t)).astype(np.float32)
    return x if ch is None else np.stack([x] * ch, axis=1)


def _f0(x):
    """Frequency of the strongest bin in the middle half."""
    x = x[len(x) // 4: 3 * len(x) // 4]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return np.argmax(spec) * SR / len(x)


def _clicks(dur=2.0, every=0.25):
    """Sharp 8 ms noise bursts — a transient test signal."""
    rng = np.random.default_rng(0)
    x = np.zeros(int(dur * SR), np.float32)
    k = np.arange(int(0.05 * SR))
    burst = (rng.standard_normal(len(k)) * np.exp(-k / (0.008 * SR))).astype(np.float32)
    ons = np.arange(0.1, dur - 0.1, every)
    for o in ons:
        i = int(o * SR)
        x[i:i + len(k)] += 0.5 * burst[:len(x) - i]
    return x, ons


class PitchShiftTests(unittest.TestCase):

    def test_shifts_pitch_and_keeps_length(self):
        x = _tone()
        y = pitch_shift(x, SR, 7)
        self.assertEqual(y.shape, x.shape)
        self.assertAlmostEqual(_f0(y), 440 * 2 ** (7 / 12), delta=3)

    def test_stereo_layout_kept_and_channels_shifted_alike(self):
        x = _tone(ch=2)
        y = pitch_shift(x, SR, -5)
        self.assertEqual(y.shape, x.shape)
        np.testing.assert_allclose(y[:, 0], y[:, 1], atol=1e-6)

    def test_tiny_shift_is_a_copy(self):
        x = _tone()
        y = pitch_shift(x, SR, 0.0)
        np.testing.assert_array_equal(x, y)
        self.assertIsNot(x, y)

    def test_deterministic(self):
        x, _ = _clicks()
        np.testing.assert_array_equal(pitch_shift(x, SR, 3), pitch_shift(x, SR, 3))

    def test_attacks_stay_sharp(self):
        # librosa's phase vocoder smeared each click into ~50-80 ms with a
        # pre-echo almost as loud as the click; Rubber Band keeps it tight.
        x, ons = _clicks()
        y = pitch_shift(x, SR, 7)
        env = np.abs(y)
        for o in ons[1:-1]:
            i = int(o * SR)
            pre = env[i - int(0.04 * SR):i - int(0.004 * SR)].max()
            peak = env[i:i + int(0.02 * SR)].max()
            self.assertLess(pre, peak * 0.25)            # pre-echo below -12 dB

    def test_pitch_curve(self):
        # A glide from 0 to +12 st: the end is an octave above the start.
        x = _tone(220, dur=3.0)
        y = pitch_shift(x, SR, np.linspace(0, 12, len(x)))
        self.assertEqual(len(y), len(x))
        n = int(0.3 * SR)
        self.assertTrue(215 < _f0(y[:n]) < 240)                 # starts near 220 Hz
        self.assertTrue(400 < _f0(y[-n:]) < 445)                # ends near 440 Hz

    def test_curve_length_must_match(self):
        with self.assertRaises(ValueError):
            pitch_shift(_tone(), SR, np.zeros(10))

    def test_empty(self):
        self.assertEqual(len(pitch_shift(np.zeros(0, np.float32), SR, 3)), 0)


class TimeStretchTests(unittest.TestCase):

    def test_length_and_pitch(self):
        x = _tone()
        for rate in (0.5, 1.5):
            y = time_stretch(x, SR, rate)
            self.assertEqual(len(y), round(len(x) / rate))
            self.assertAlmostEqual(_f0(y), 440, delta=3)

    def test_rate_curve_length_is_exact(self):
        x = _tone(dur=3.0)
        rate = np.linspace(1.0, 0.5, len(x))
        y = time_stretch(x, SR, rate)
        self.assertEqual(len(y), int(round(np.sum(1.0 / rate))))
        # The end of the stretched audio is real content, not padding
        self.assertGreater(np.abs(y[-int(0.2 * SR):-int(0.05 * SR)]).max(), 0.1)

    def test_transform_both_at_once(self):
        x = _tone()
        y = transform(x, SR, rate=1.25, semitones=-12)
        self.assertEqual(len(y), round(len(x) / 1.25))
        self.assertAlmostEqual(_f0(y), 220, delta=3)


class TempoRampTests(unittest.TestCase):

    def test_ritardando_lengthens_and_map_matches_audio(self):
        mix = _tone(dur=4.0, ch=2)
        out, tmap = _stretch_mix_by_tempo(mix, SR, [{'from': 1.0, 'to': 3.0, 'factor': 0.5, 'shape': 'ramp'}])
        # 2 s ramping 1 → 0.5: ∫ 1/r = 2 * ln(2) / 0.5 ≈ 2.77 s
        self.assertAlmostEqual(len(out) / SR, 1.0 + 2 * np.log(2) / 0.5 + 1.0, delta=0.02)
        self.assertAlmostEqual(tmap[-1][1], len(out) / SR, delta=0.002)
        self.assertEqual(out.shape[1], 2)
        self.assertAlmostEqual(_f0(out[:, 0]), 440, delta=3)


class HelperTests(unittest.TestCase):

    def test_read_at_rate(self):
        x = _tone()
        y = read_at_rate(x, 0, len(x) // 2, 2.0)                # octave up, tape-style
        self.assertAlmostEqual(_f0(y), 880, delta=6)
        self.assertEqual(read_at_rate(x, len(x) - 10, 50, 1.0)[20:].max(), 0.0)   # past the end: silent

    def test_steps_to_curve(self):
        c = steps_to_curve([0.0, 1.0], hop=100, n=200)
        self.assertEqual(len(c), 200)
        self.assertEqual(c[0], 0.0)
        self.assertEqual(c[-1], 1.0)
        self.assertAlmostEqual(c[100], 0.5, places=2)           # glide centred on the boundary
        self.assertTrue(np.all(np.diff(c) >= 0))

    def test_parallel_map_matches_serial(self):
        x = _tone(dur=0.5)
        shifts = [-7.0, -3.0, 2.0, 5.0]
        par = parallel_map(lambda s: pitch_shift(x, SR, s), shifts)
        for s, y in zip(shifts, par):
            np.testing.assert_array_equal(y, pitch_shift(x, SR, s))


if __name__ == '__main__':
    unittest.main()
