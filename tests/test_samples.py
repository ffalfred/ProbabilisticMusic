"""Samples are cut on the timeline, so tracks that start later slice correctly.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
import soundfile as sf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.sample_engine import build_bank

SR = 8000


class TrackOffsetTests(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # A "ramp" track: sample k has value k, so a slice shows where it came from
        ramp = (np.arange(5 * SR) / (5 * SR)).astype(np.float32)
        self.ramp = ramp
        self.base = os.path.join(self.dir, 'base.wav')
        self.late = os.path.join(self.dir, 'late.wav')
        sf.write(self.base, np.zeros(20 * SR, np.float32), SR, subtype='FLOAT')
        sf.write(self.late, ramp, SR, subtype='FLOAT')

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _bank(self, samples):
        score = {'tracks': [{'path': self.base}, {'path': self.late, 'from': 10.0}],
                 'samples': samples}
        return build_bank(score)[0]

    def test_sample_on_a_late_track_is_cut_from_its_own_time(self):
        # Marked at 12-13 s on the timeline = the late track's own 2-3 s
        bank = self._bank({'s': {'from': 12.0, 'to': 13.0, 'track': 1}})
        np.testing.assert_allclose(bank['s'][:, 0], self.ramp[2 * SR:3 * SR])

    def test_parts_outside_the_track_are_silent_and_length_is_kept(self):
        bank = self._bank({'before': {'from': 9.5, 'to': 10.5, 'track': 1},
                           'after':  {'from': 14.5, 'to': 15.5, 'track': 1},
                           'none':   {'from': 1.0, 'to': 2.0, 'track': 1}})
        b, a, n = bank['before'][:, 0], bank['after'][:, 0], bank['none'][:, 0]
        self.assertEqual(len(b), SR)
        self.assertEqual(len(a), SR)
        np.testing.assert_array_equal(b[:SR // 2], 0)                       # before the track starts
        np.testing.assert_allclose(b[SR // 2:], self.ramp[:SR // 2])
        np.testing.assert_allclose(a[:SR // 2], self.ramp[-SR // 2:])
        np.testing.assert_array_equal(a[SR // 2:], 0)                       # after it ends
        np.testing.assert_array_equal(n, 0)                                 # entirely before it

    def test_tracks_at_zero_are_unchanged(self):
        sf.write(self.base, np.tile(self.ramp, 4), SR, subtype='FLOAT')
        bank = self._bank({'s': {'from': 2.0, 'to': 3.0}})
        np.testing.assert_allclose(bank['s'][:, 0], self.ramp[2 * SR:3 * SR])



class CarryFromTrackTests(unittest.TestCase):
    """`include`: which of the track's stages (FX chain, FX regions,
    automation, gain) a sample carries."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.raw = (0.2 * np.sin(2 * np.pi * 300 * np.arange(4 * SR) / SR)).astype(np.float32)
        self.path = os.path.join(self.dir, 't.wav')
        sf.write(self.path, self.raw, SR, subtype='FLOAT')
        self.track = {'path': self.path, 'gain_db': -6.0,
                      'fx': [{'type': 'tremolo', 'rate': 4, 'depth': 0.8}],
                      'automation': [{'t': 0, 'db': 0}, {'t': 4, 'db': -20}],
                      'fx_regions': [{'from': 1.0, 'to': 3.0, 'fx': [{'type': 'filter', 'cutoff': 200}]}]}

    def tearDown(self):
        shutil.rmtree(self.dir)

    def _bank(self, samples, **track):
        return build_bank({'tracks': [dict(self.track, **track)], 'samples': samples})

    def test_none_is_the_file_and_default_is_the_fx_chain(self):
        bank, _, _ = self._bank({'raw': {'from': 1.5, 'to': 2.0, 'include': 'none'},
                                 'dflt': {'from': 1.5, 'to': 2.0}})
        np.testing.assert_allclose(bank['raw'][:, 0], self.raw[int(1.5 * SR):int(2.0 * SR)])
        self.assertFalse(np.allclose(bank['dflt'], bank['raw']))                # tremolo carried
        only_fx, _, _ = self._bank({'s': {'from': 1.5, 'to': 2.0, 'include': ['fx']}})
        np.testing.assert_array_equal(only_fx['s'], bank['dflt'])

    def test_all_is_what_you_hear_on_the_track(self):
        bank, sr, base = self._bank({'s': {'from': 1.5, 'to': 2.0, 'include': 'all'}})
        np.testing.assert_allclose(bank['s'], base[int(1.5 * SR):int(2.0 * SR)], atol=1e-6)

    def test_single_stage(self):
        bank, _, _ = self._bank({'s': {'from': 0.2, 'to': 0.6, 'include': ['gain']}})
        np.testing.assert_allclose(bank['s'][:, 0], self.raw[int(0.2 * SR):int(0.6 * SR)] * 10 ** (-6 / 20),
                                   atol=1e-6)

    def test_a_muted_track_can_still_be_sampled(self):
        bank, _, base = self._bank({'s': {'from': 0.2, 'to': 0.6, 'include': 'none'}}, muted=True)
        self.assertEqual(float(np.abs(base).max()), 0.0)                        # silent in the mix
        np.testing.assert_allclose(bank['s'][:, 0], self.raw[int(0.2 * SR):int(0.6 * SR)])


if __name__ == '__main__':
    unittest.main()
