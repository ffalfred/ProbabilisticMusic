"""Parallel event processing and the render cache (src/render_cache.py).

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

from src import render_cache
from src.mixer import mix_events

SR = 22050


def _tone(f, dur, amp=0.2):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)[:, None]


BANK = {'a': _tone(220, 0.6), 'b': _tone(330, 0.4), 'c': _tone(440, 0.5)}
SCORE = {'samples': {k: {} for k in BANK}}


def _events(random_fx=False):
    evs = [{'t': 0.2 + 0.4 * i, 'sample': 'abc'[i % 3], 'gain_db': -6,
            'pitch': [0, 3, -5][i % 3], 'fx': [{'type': 'filter', 'cutoff': 1500}] if i % 2 else []}
           for i in range(8)]
    if random_fx:
        evs[3]['fx'] = [{'type': 'morpho_grain_scatter', 'pitch_spread': 12, 'shuffle_pct': 80}]
    return evs


def _render(events, seed):
    np.random.seed(seed)
    base = np.zeros((5 * SR, 1), np.float32)
    return mix_events([dict(e) for e in events], dict(BANK), SR, SCORE, base)


class DeterminismTests(unittest.TestCase):

    def test_same_seed_same_audio_cold_warm_and_parallel(self):
        evs = _events(random_fx=True)
        render_cache.clear()
        cold = _render(evs, 7)
        render_cache.clear()
        cold2 = _render(evs, 7)
        warm = _render(evs, 7)                                  # everything from the cache
        np.testing.assert_array_equal(cold, cold2)
        np.testing.assert_array_equal(cold, warm)

    def test_random_effects_still_change_with_the_seed(self):
        evs = _events(random_fx=True)
        render_cache.clear()
        a, b = _render(evs, 1), _render(evs, 2)
        seg = slice(int(1.4 * SR), int(1.9 * SR))              # the grain-scatter event (t = 1.4)
        self.assertFalse(np.allclose(a[seg], b[seg]))
        rest = slice(0, int(1.3 * SR))                          # deterministic events agree
        np.testing.assert_array_equal(a[rest], b[rest])


class ReuseTests(unittest.TestCase):

    def test_unchanged_events_are_reused_with_a_new_seed(self):
        evs = _events()
        render_cache.clear()
        _render(evs, 1)
        before = dict(render_cache.stats)
        _render(evs, 2)                                         # new seed, nothing random
        self.assertEqual(render_cache.stats['hits'] - before['hits'], len(evs))
        self.assertEqual(render_cache.stats['misses'], before['misses'])

    def test_an_edit_reprocesses_only_that_event(self):
        evs = _events()
        render_cache.clear()
        a = _render(evs, 1)
        before = dict(render_cache.stats)
        evs[4]['gain_db'] = 0                                   # louder
        evs[6]['t'] += 0.1                                      # moved: reused
        b = _render(evs, 1)
        self.assertEqual(render_cache.stats['misses'] - before['misses'], 1)
        diff = np.abs(a - b)[:, 0]
        changed = np.flatnonzero(diff > 1e-7)
        self.assertGreater(changed.min(), int(1.8 * SR) - 1)    # nothing before event 4 changed

    def test_cached_audio_is_never_modified(self):
        evs = _events()
        render_cache.clear()
        first = _render(evs, 3)
        for _ in range(3):
            np.testing.assert_array_equal(_render(evs, 3), first)


if __name__ == '__main__':
    unittest.main()
