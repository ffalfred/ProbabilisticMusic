"""Output loudness: measurement, safety brake, export adjustment.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.loudness import measure_lufs, brake, finish, peak_db, options_from


def _tone(sr, dur, amp=1.0, freq=997.0):
    t = np.arange(int(dur * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class LoudnessTests(unittest.TestCase):

    def test_measure_matches_bs1770_reference(self):
        # BS.1770: a 0 dBFS 997 Hz sine reads -3.01 LUFS on one channel and
        # 0 LUFS on both; level changes map 1:1.
        for sr in (48000, 44100):
            s = _tone(sr, 5.0)
            self.assertAlmostEqual(measure_lufs(s, sr), -3.01, delta=0.1)
            st = np.stack([s, s], axis=1)
            self.assertAlmostEqual(measure_lufs(st, sr), 0.0, delta=0.1)
            self.assertAlmostEqual(measure_lufs(st * 0.1, sr), -20.0, delta=0.1)

    def test_silence_and_gating(self):
        sr = 44100
        self.assertEqual(measure_lufs(np.zeros(sr * 2, np.float32), sr), float('-inf'))
        # Long silence around a tone does not drag the reading down (gates)
        s = _tone(sr, 10.0, 0.5)
        padded = np.concatenate([np.zeros(sr * 10, np.float32), s, np.zeros(sr * 10, np.float32)])
        self.assertAlmostEqual(measure_lufs(padded, sr), measure_lufs(s, sr), delta=0.2)

    def test_brake_leaves_quiet_audio_alone(self):
        sr = 22050
        x = _tone(sr, 1.0, 0.8)
        y, red = brake(x, sr)
        self.assertIs(y, x)
        self.assertEqual(red, 0.0)

    def test_brake_holds_the_ceiling_and_only_touches_the_peaks(self):
        sr = 22050
        q = _tone(sr, 1.0, 0.3, 220)
        x = np.concatenate([q, q * 5, q, q, q])        # one loud second
        y, red = brake(x, sr)
        self.assertLessEqual(peak_db(y), -1.0 + 1e-4)
        self.assertAlmostEqual(red, 20 * np.log10(1.5 / 10 ** (-1 / 20)), delta=0.1)
        # Before the loud part (minus the look-ahead) and well after the
        # release, the audio is bit-identical.
        np.testing.assert_array_equal(y[:sr - int(0.01 * sr)], x[:sr - int(0.01 * sr)])
        np.testing.assert_array_equal(y[-sr:], x[-sr:])

    def test_brake_keeps_the_stereo_image(self):
        sr = 22050
        s = _tone(sr, 1.0, 2.0, 220)
        x = np.stack([s, 0.5 * s], axis=1)
        y, _ = brake(x, sr)
        loud = np.abs(x[:, 0]) > 0.1
        np.testing.assert_allclose(y[loud, 1] / y[loud, 0], 0.5, atol=1e-5)

    def test_finish_target_and_source(self):
        sr = 44100
        x = np.stack([_tone(sr, 4.0, 0.05, 440)] * 2, axis=1)
        y, rep = finish(x, sr, adjust='target', target_lufs=-23, use_brake=True)
        self.assertAlmostEqual(measure_lufs(y, sr), -23.0, delta=0.05)
        self.assertEqual(rep['brake_db'], 0.0)
        src = x * 4
        y, rep = finish(x, sr, adjust='source', source=src, use_brake=False)
        self.assertAlmostEqual(rep['gain_db'], 20 * np.log10(4), delta=0.05)
        # 'none' leaves the level alone
        y, rep = finish(x, sr)
        np.testing.assert_array_equal(y, x)
        self.assertEqual(rep['gain_db'], 0.0)

    def test_finish_on_silence(self):
        y, rep = finish(np.zeros((1000, 2), np.float32), 22050, adjust='target', target_lufs=-14)
        self.assertIsNone(rep['lufs'])
        self.assertEqual(rep['gain_db'], 0.0)

    def test_options(self):
        self.assertEqual(options_from(None), {'adjust': 'none', 'target_lufs': None, 'use_brake': True})
        self.assertEqual(options_from({'adjust': 'target'})['target_lufs'], -14.0)
        self.assertEqual(options_from({'adjust': 'target', 'target_lufs': 'broadcast'})['target_lufs'], -23.0)
        self.assertFalse(options_from({'brake': False})['use_brake'])
        self.assertEqual(options_from({'adjust': 'bogus'})['adjust'], 'none')


if __name__ == '__main__':
    unittest.main()
