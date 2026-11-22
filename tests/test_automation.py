"""Fade shapes and effect automation (src/envelope.fade_ramp, src/automation.py).

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest
import warnings

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
warnings.filterwarnings('ignore')

from src.envelope import fade_ramp, apply_fade, build_phrase_envelope
from src.fx import apply_fx

SR = 22050


def _tone(f=440.0, dur=4.0, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)[:, None]


def _noise(dur=4.0):
    return (np.random.default_rng(0).standard_normal(int(dur * SR)) * 0.2).astype(np.float32)[:, None]


def _rms(x, a, b):
    seg = x[int(a * SR):int(b * SR)]
    return float(np.sqrt(np.mean(seg ** 2)))


def _hf(x, a, b, above=2000):
    """dB of the energy above `above` Hz, relative to all, between a and b s."""
    seg = x[int(a * SR):int(b * SR), 0]
    S = np.abs(np.fft.rfft(seg)) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return 10 * np.log10(S[f > above].sum() / S.sum())


class FadeShapeTests(unittest.TestCase):

    def test_shapes(self):
        n = 1001
        mid = n // 2
        self.assertAlmostEqual(float(fade_ramp(n, 'linear')[mid]), 0.5, places=3)
        self.assertAlmostEqual(float(fade_ramp(n, 'smooth')[mid]), np.sqrt(0.5), places=3)   # equal power
        self.assertAlmostEqual(float(fade_ramp(n, 's-curve')[mid]), 0.5, places=3)
        self.assertLess(float(fade_ramp(n, 'exponential')[mid]), 0.05)   # -30 dB at half way
        for c in ('linear', 'smooth', 's-curve', 'exponential'):
            r = fade_ramp(n, c)
            self.assertEqual(float(r[0]), 0.0)
            self.assertAlmostEqual(float(r[-1]), 1.0, places=6)
            self.assertTrue(np.all(np.diff(r) >= 0))

    def test_smooth_is_the_default_and_keeps_power_in_a_crossfade(self):
        n = 1000
        fi = fade_ramp(n)
        fo = fade_ramp(n)[::-1]
        np.testing.assert_allclose(fi ** 2 + fo ** 2, 1.0, atol=1e-6)
        clip = np.ones((n, 1), np.float32)
        np.testing.assert_allclose(apply_fade(clip.copy(), SR, 0.5, 0.0)[:500, 0], fade_ramp(500), atol=1e-6)

    def test_fade_curve_options_reach_fades(self):
        clip = np.ones((1000, 1), np.float32)
        lin = apply_fade(clip.copy(), SR, 0.5, 0.0, curve='linear')
        np.testing.assert_allclose(lin[:500, 0], np.linspace(0, 1, 500), atol=1e-6)
        env = build_phrase_envelope(1000, SR, [{'from': 0, 'to': 1000 / SR, 'fade_in': 0.5, 'fade_curve': 'linear'}])
        np.testing.assert_allclose(env[:500], np.linspace(0, 1, 500), atol=1e-6)


class ExactAutomationTests(unittest.TestCase):

    def test_constant_curve_equals_a_fixed_setting(self):
        x = _noise()
        for fx in ({'type': 'filter', 'cutoff': 800}, {'type': 'tremolo', 'rate': 5, 'depth': 0.5},
                   {'type': 'delay', 'time': 0.3, 'wet': 0.4}):
            key = {'filter': 'cutoff', 'tremolo': 'rate', 'delay': 'wet'}[fx['type']]
            curved = dict(fx, **{key: {'curve': [[0, fx[key]], [3, fx[key]]]}})
            with self.subTest(fx['type']):
                np.testing.assert_allclose(apply_fx(x, SR, [curved]), apply_fx(x, SR, [fx]), atol=1e-5)

    def test_filter_sweep_opens(self):
        y = apply_fx(_noise(), SR, [{'type': 'filter', 'cutoff': {'curve': [[0, 200], [4, 6000]]}}])
        self.assertLess(_hf(y, 0.2, 0.8), _hf(y, 3.2, 3.8) - 10)

    def test_reverb_swells_in(self):
        x = _tone()
        dry = apply_fx(x, SR, [{'type': 'reverb', 'reverberance': 50, 'wet': 0}])
        y = apply_fx(x, SR, [{'type': 'reverb', 'reverberance': 50, 'wet': {'curve': [[0, 0], [4, 1]]}}])
        self.assertLess(_rms(y - dry[:len(y)] if len(dry) >= len(y) else y[:len(dry)] - dry, 0.1, 0.6),
                        0.3 * _rms(y[:len(dry)] - dry, 3.2, 3.9))

    def test_delay_echoes_keep_their_send_level(self):
        click = np.zeros((int(3 * SR), 1), np.float32)
        click[0] = click[int(1.0 * SR)] = 1.0
        y = apply_fx(click, SR, [{'type': 'delay', 'time': 0.25, 'feedback': 0.5, 'dry': 1,
                                  'wet': {'curve': [[0, 0.8], [0.9, 0.8], [1.0, 0.2], [3, 0.2]]}}])
        d = int(0.25 * SR)
        self.assertAlmostEqual(float(y[d, 0]), 0.8, places=4)                # sent at 0.8
        self.assertAlmostEqual(float(y[int(1.0 * SR) + d, 0]), 0.2, places=4)  # sent at 0.2
        self.assertAlmostEqual(float(y[2 * d, 0]), 0.4, places=4)            # 0.8 × feedback

    def test_plugin_dry_wet_ramp(self):
        x = _tone()
        y = apply_fx(x, SR, [{'type': 'morpho_inharmonic', 'shift_hz': 100, 'dry_wet': {'curve': [[0, 0], [4, 100]]}}])
        np.testing.assert_allclose(y[:100], x[:100], atol=2e-3)            # starts dry
        full = apply_fx(x, SR, [{'type': 'morpho_inharmonic', 'shift_hz': 100, 'dry_wet': 100}])
        n = min(len(y), len(full))
        np.testing.assert_allclose(y[n - 100:n], full[n - 100:n], atol=2e-3)   # ends fully wet


class ApproximateAutomationTests(unittest.TestCase):

    def test_any_setting_can_move(self):
        y = apply_fx(_tone(), SR, [{'type': 'overdrive', 'drive': {'curve': [[0, 0.0], [4, 1.0]]}}])
        self.assertGreater(_hf(y, 3.2, 3.8, 600), _hf(y, 0.2, 0.8, 600) + 3)   # more harmonics later

    def test_matches_fixed_renders_at_the_curve_points(self):
        x = _tone(dur=2.0)
        y = apply_fx(x, SR, [{'type': 'overdrive', 'drive': {'curve': [[0, 0.2], [2, 0.9]]}}])
        lo = apply_fx(x, SR, [{'type': 'overdrive', 'drive': 0.2}])
        hi = apply_fx(x, SR, [{'type': 'overdrive', 'drive': 0.9}])
        np.testing.assert_allclose(y[:1], lo[:1], atol=1e-5)
        np.testing.assert_allclose(y[len(hi) - 1:len(hi)], hi[-1:], atol=1e-5)

    def test_plugin_settings_too(self):
        y = apply_fx(_tone(), SR, [{'type': 'morpho_inharmonic', 'shift_hz': {'curve': [[0, 0], [4, 300]]},
                                   'dry_wet': 100}])
        self.assertEqual(y.shape[1], 1)
        self.assertTrue(np.isfinite(y).all())


if __name__ == '__main__':
    unittest.main()
