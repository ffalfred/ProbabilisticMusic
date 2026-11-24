"""Golem mix dimensions: stereo width and reverb (src/mixer._apply_state_to_mix).

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import shutil
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.mixer import _apply_state_to_mix

SR = 22050


def _trace(dim, value, dur=2.0):
    s = [0.0] * 12
    s[dim] = value
    return [{'t': 0.0, 'sample': list(s)}, {'t': dur, 'sample': list(s)}]


def _stereo(dur=2.0):
    t = np.arange(int(dur * SR)) / SR
    return np.stack([0.3 * np.sin(2 * np.pi * 220 * t), 0.2 * np.sin(2 * np.pi * 330 * t)], axis=1).astype(np.float32)


class WidthTests(unittest.TestCase):

    def test_width_maps_mono_recorded_wide(self):
        x = _stereo()
        mid, side = (x[:, 0] + x[:, 1]) / 2, (x[:, 0] - x[:, 1]) / 2
        mono = _apply_state_to_mix(x, SR, _trace(8, 0.0), ['stereo_width'])
        np.testing.assert_allclose(mono[:, 0], mono[:, 1], atol=1e-6)
        same = _apply_state_to_mix(x, SR, _trace(8, 0.5), ['stereo_width'])
        np.testing.assert_allclose(same, x, atol=1e-6)
        wide = _apply_state_to_mix(x, SR, _trace(8, 1.0), ['stereo_width'])
        np.testing.assert_allclose((wide[:, 0] - wide[:, 1]) / 2, 2 * side, atol=1e-6)
        np.testing.assert_allclose((wide[:, 0] + wide[:, 1]) / 2, mid, atol=1e-6)

    def test_width_leaves_mono_pieces_alone(self):
        x = _stereo()[:, :1]
        np.testing.assert_array_equal(_apply_state_to_mix(x, SR, _trace(8, 1.0), ['stereo_width']), x)

    def test_width_only_when_enabled(self):
        x = _stereo()
        np.testing.assert_array_equal(_apply_state_to_mix(x, SR, _trace(8, 1.0), ['gain_db']), x)


@unittest.skipUnless(shutil.which('sox'), 'needs sox')
class ReverbTests(unittest.TestCase):

    def test_reverb_adds_on_top_and_rings_on(self):
        x = _stereo(1.0)
        y = _apply_state_to_mix(x, SR, _trace(5, 0.6, 1.0), ['reverb_wet'])
        self.assertGreater(len(y), len(x) + SR // 2)                   # the tail rings past the end
        # The original is still there at full level: removing it leaves only
        # reverb, which is quieter than the original at wet 0.6
        added = y[:len(x)] - x
        self.assertLess(np.sqrt(np.mean(added ** 2)), 0.75 * np.sqrt(np.mean(x ** 2)))
        self.assertGreater(np.sqrt(np.mean(added ** 2)), 0.3 * np.sqrt(np.mean(x ** 2)))

    def test_reverb_zero_keeps_the_original(self):
        x = _stereo(1.0)
        y = _apply_state_to_mix(x, SR, _trace(5, 0.0, 1.0), ['reverb_wet'])
        np.testing.assert_allclose(y[:len(x)], x, atol=1e-6)
        self.assertEqual(float(np.abs(y[len(x):]).max(initial=0.0)), 0.0)


if __name__ == '__main__':
    unittest.main()
