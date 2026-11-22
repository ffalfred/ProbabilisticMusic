"""Reverb and delay: dry/wet levels, echo levels, reverb tails.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import shutil
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.fx import apply_fx, reverb_wet, _rms

SR = 22050


def _pluck(dur=0.1, total=0.2):
    """A short note (decays within `dur`) inside a clip of `total` seconds."""
    t = np.arange(int(total * SR)) / SR
    x = 0.3 * np.sin(2 * np.pi * 440 * t) * np.exp(-t * 40)
    x[t > dur] = 0
    return x.astype(np.float32)[:, None]


def _peak(x):
    return float(np.max(np.abs(x))) if len(x) else 0.0


class DelayTests(unittest.TestCase):

    def test_echo_levels_follow_wet_and_feedback(self):
        note = _pluck()
        out = apply_fx(note, SR, [{'type': 'delay', 'time': 0.25, 'feedback': 0.6, 'dry': 1, 'wet': 0.5}])
        d = int(0.25 * SR)
        levels = [_peak(out[k * d:k * d + len(note)]) / _peak(note) for k in range(4)]
        np.testing.assert_allclose(levels, [1.0, 0.5, 0.3, 0.18], atol=1e-4)
        np.testing.assert_array_equal(out[:len(note)], note)          # original untouched

    def test_dry_zero_leaves_only_the_echoes(self):
        note = _pluck()
        out = apply_fx(note, SR, [{'type': 'delay', 'time': 0.25, 'dry': 0, 'wet': 1}])
        self.assertEqual(_peak(out[:len(note)]), 0.0)
        self.assertAlmostEqual(_peak(out[int(0.25 * SR):]) / _peak(note), 1.0, places=4)

    def test_echoes_ring_out_instead_of_stopping_after_eight(self):
        note = _pluck()
        out = apply_fx(note, SR, [{'type': 'delay', 'time': 0.1, 'feedback': 0.9, 'wet': 0.5}])
        # 0.5 * 0.9^k reaches -60 dB after ~60 echoes (6 s), not 8 (0.8 s)
        self.assertGreater(len(out) / SR, 5.0)
        last = out[-int(0.1 * SR):]
        self.assertLess(_peak(last) / _peak(note), 2e-3)


@unittest.skipUnless(shutil.which('sox'), 'needs sox')
class ReverbTests(unittest.TestCase):

    def test_wet_zero_is_the_original(self):
        note = _pluck()
        out = apply_fx(note, SR, [{'type': 'reverb', 'wet': 0}])
        np.testing.assert_array_equal(out, note)

    def test_original_kept_and_tail_rings_past_the_clip(self):
        note = _pluck(total=0.5)
        fx = {'type': 'reverb', 'reverberance': 50, 'dry': 1, 'wet': 0.5}
        out = apply_fx(note, SR, [fx])
        self.assertGreater(len(out) / SR, 1.5)              # ~2 s tail, not cut at 0.5 s
        wet = reverb_wet(note, SR, fx)
        np.testing.assert_allclose(out[:len(note)], note + 0.5 * wet[:len(note)], atol=1e-6)
        # The tail dies away: it ends 60 dB down, faded, not chopped
        self.assertLess(_peak(out[-int(0.02 * SR):]), _peak(out) * 1e-3)

    def test_wet_one_is_as_loud_as_the_original(self):
        note = _pluck(total=0.5)
        out = apply_fx(note, SR, [{'type': 'reverb', 'reverberance': 50, 'dry': 0, 'wet': 1}])
        self.assertAlmostEqual(_rms(out[:len(note)]) / _rms(note), 1.0, places=3)

    def test_long_reverb_gets_room(self):
        # reverberance 100 rings ~11 s: the padding must grow to fit it
        note = _pluck()
        wet = reverb_wet(note, SR, {'reverberance': 100, 'room_scale': 100})
        self.assertGreater(len(wet) / SR, 8.0)
        self.assertLess(_peak(wet[-int(0.02 * SR):]), _peak(wet) * 1e-3)


if __name__ == '__main__':
    unittest.main()
