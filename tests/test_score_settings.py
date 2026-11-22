"""Output FX (fx_global), output FX zones (fx_sections), silence_end, and
muted entries in saved scores.

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

from src.renderer import render_mix, _apply_phrase_tempo

SR = 22050
HI = 2000.0                                     # a tone a 100 Hz low-pass removes
LOWPASS = [{'type': 'filter', 'cutoff': 100}]


def _tone(f, dur, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)[:, None]


def _rms(x, a, b):
    seg = x[int(a * SR):int(b * SR)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


def _render(score, events=(), bank=None, base=None, dur=4.0):
    base = _tone(HI, dur) if base is None else base
    score = _apply_phrase_tempo(dict(score))
    return render_mix(score, bank or {}, [dict(e) for e in events], SR, base)


class OutputFxTests(unittest.TestCase):

    def test_output_zone_affects_events_source_zone_does_not(self):
        bank = {'e': _tone(HI, 1.0)}
        ev = [{'t': 1.5, 'sample': 'e', 'gain_db': 0}]
        silent = np.zeros((4 * SR, 1), np.float32)
        src_zone, _ = _render({'samples': {'e': {}}, 'fx_ranges': [{'from': 1.0, 'to': 3.0, 'fx': LOWPASS}]},
                              ev, bank, silent)
        out_zone, _ = _render({'samples': {'e': {}}, 'fx_sections': [{'from': 1.0, 'to': 3.0, 'fx': LOWPASS}]},
                              ev, bank, silent)
        self.assertGreater(_rms(src_zone, 1.7, 2.3), 0.1)       # the event plays on top, unfiltered
        self.assertLess(_rms(out_zone, 1.7, 2.3), 0.01)         # filtered with everything else

    def test_output_zone_tail_rings_past_its_end(self):
        y, _ = _render({'fx_sections': [{'from': 1.0, 'to': 1.5, 'fx': [{'type': 'delay', 'time': 0.4, 'dry': 1, 'wet': 0.8}]}]},
                       base=np.pad(_tone(HI, 0.5), ((SR, int(2.5 * SR)), (0, 0))))
        self.assertGreater(_rms(y, 1.95, 2.25), 0.05)           # an echo after the zone ended

    def test_output_zone_sits_where_it_is_drawn_after_a_ritardando(self):
        # 0-2 s at half speed takes ~2.77 s of real time: a section drawn at
        # 3-3.5 s (score time) must be filtered at ~3.77-4.27 s
        score = {'tempo': [{'from': 0.0, 'to': 2.0, 'factor': 0.5, 'shape': 'ramp'}],
                 'fx_sections': [{'from': 3.0, 'to': 3.5, 'fx': LOWPASS}]}
        y, tmap = _render(score, dur=5.0)
        start = 3.0 + (tmap[-1][1] - tmap[-1][0])
        self.assertLess(_rms(y, start + 0.1, start + 0.4), 0.01)
        self.assertGreater(_rms(y, 3.1, 3.4), 0.1)              # not at the unmapped position

    def test_old_single_effect_sections_still_work(self):
        y, _ = _render({'fx_sections': [{'from': 1.0, 'to': 2.0, 'type': 'filter', 'cutoff': 100}]})
        self.assertLess(_rms(y, 1.2, 1.8), 0.01)
        self.assertGreater(_rms(y, 2.2, 3.0), 0.1)

    def test_output_fx_on_everything(self):
        bank = {'e': _tone(HI, 1.0)}
        y, _ = _render({'samples': {'e': {}}, 'fx_global': LOWPASS},
                       [{'t': 1.0, 'sample': 'e', 'gain_db': 0}], bank)
        self.assertLess(_rms(y, 0.5, 3.5), 0.01)


class SilenceAndMuteTests(unittest.TestCase):

    def test_silence_end_adds_silence_after_the_piece(self):
        plain, _ = _render({})
        y, _ = _render({'silence_end': 1.5})
        self.assertEqual(len(y), len(plain) + int(1.5 * SR))
        self.assertEqual(float(np.abs(y[len(plain):]).max()), 0.0)

    def test_muted_entries_in_a_saved_score_are_left_out(self):
        plain, tm0 = _render({})
        y, tm = _render({'fx_ranges': [{'from': 1.0, 'to': 2.0, 'fx': LOWPASS, 'muted': True}],
                         'fx_sections': [{'from': 1.0, 'to': 2.0, 'fx': LOWPASS, 'muted': True}],
                         'tempo': [{'from': 0.0, 'to': 2.0, 'factor': 0.5, 'muted': True}],
                         'phrases': [{'from': 0.0, 'to': 2.0, 'tempo_factor': 0.5, 'gain_db': -20, 'muted': True}]})
        np.testing.assert_array_equal(y, plain)
        self.assertEqual(tm, tm0)


if __name__ == '__main__':
    unittest.main()
