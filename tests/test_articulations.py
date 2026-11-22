"""Articulations on events and on the whole mix (src/articulations.py).

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

from src.mixer import mix_events
from src.renderer import render_mix

SR = 22050


def _tone(f, dur, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * f * t)).astype(np.float32)[:, None]


def _level(x, f, a, b):
    """Amplitude of the f Hz component of x between a and b seconds."""
    seg = x[int(a * SR):int(b * SR), 0].astype(np.float64)
    t = np.arange(len(seg)) / SR
    return 2 * abs(np.mean(seg * np.exp(-2j * np.pi * f * t)))


def _rms(x, a, b):
    seg = x[int(a * SR):int(b * SR)]
    return float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0


BASE_F, EVENT_F = 330.0, 220.0


def _render(arts, events=None, bank=None, base=None, dur=4.0):
    bank = bank or {'e': _tone(EVENT_F, 1.0)}
    events = events or [{'t': 1.0, 'sample': 'e', 'gain_db': 0}]
    base = _tone(BASE_F, dur) if base is None else base
    score = {'samples': {k: {'fade_in': 0.01, 'fade_out': 0.01} for k in bank},
             'articulations': arts}
    return mix_events([dict(e) for e in events], bank, SR, score, base)


class EventTargetTests(unittest.TestCase):

    def test_staccato_shortens_the_event_and_leaves_the_source(self):
        plain = _render([])
        y = _render([{'type': 'staccato', 't': 1.0}])
        self.assertGreater(_level(plain, EVENT_F, 1.4, 1.8), 0.2)
        self.assertLess(_level(y, EVENT_F, 1.3, 1.8), 0.01)           # cut after 0.15 s
        self.assertGreater(_level(y, EVENT_F, 1.02, 1.12), 0.2)        # its start is kept
        # The source plays on untouched (the old staccato cut a hole in it)
        np.testing.assert_allclose(y[:int(1.0 * SR)], plain[:int(1.0 * SR)])
        self.assertAlmostEqual(_level(y, BASE_F, 1.3, 1.8), _level(plain, BASE_F, 1.3, 1.8), places=3)

    def test_staccato_length_is_adjustable(self):
        y = _render([{'type': 'staccato', 't': 1.0, 'keep_s': 0.5}])
        self.assertGreater(_level(y, EVENT_F, 1.3, 1.45), 0.2)
        self.assertLess(_level(y, EVENT_F, 1.6, 1.9), 0.01)

    def test_point_mark_needs_an_event_nearby(self):
        plain = _render([])
        np.testing.assert_array_equal(_render([{'type': 'staccato', 't': 2.0}]), plain)   # 1 s away
        self.assertLess(_level(_render([{'type': 'staccato', 't': 1.4}]), EVENT_F, 1.3, 1.8), 0.01)

    def test_range_marks_every_event_starting_inside(self):
        events = [{'t': 0.5, 'sample': 'e', 'gain_db': 0}, {'t': 2.0, 'sample': 'e', 'gain_db': 0}]
        y = _render([{'type': 'staccato', 'from': 0.0, 'to': 1.0}], events=events)
        self.assertLess(_level(y, EVENT_F, 0.8, 1.4), 0.01)            # first event cut
        self.assertGreater(_level(y, EVENT_F, 2.3, 2.9), 0.2)          # second untouched

    def test_accent_boosts_the_event_attack_only(self):
        plain = _render([])
        y = _render([{'type': 'accent', 't': 1.0}])
        e_plain = _rms(plain - _render([], events=[{'t': 1.0, 'sample': 'e', 'gain_db': -120}]), 1.01, 1.04)
        e_acc = _rms(y - _render([], events=[{'t': 1.0, 'sample': 'e', 'gain_db': -120}]), 1.01, 1.04)
        self.assertGreater(e_acc / e_plain, 1.4)                       # ~ +4 dB on average
        np.testing.assert_allclose(y[int(1.1 * SR):], plain[int(1.1 * SR):], atol=1e-6)

    def test_legato_rings_into_the_next_event(self):
        bank = {'e': _tone(EVENT_F, 0.3), 'n': _tone(440.0, 0.5)}
        events = [{'t': 0.5, 'sample': 'e', 'gain_db': 0}, {'t': 1.5, 'sample': 'n', 'gain_db': 0}]
        plain = _render([], events=events, bank=bank)
        y = _render([{'type': 'legato', 'from': 0.4, 'to': 0.6}], events=events, bank=bank)
        self.assertLess(_level(plain, EVENT_F, 1.0, 1.4), 0.01)        # sample ran out at 0.8 s
        self.assertGreater(_level(y, EVENT_F, 1.0, 1.4), 0.2)          # held until the next event
        self.assertLess(_level(y, EVENT_F, 1.75, 2.0), 0.01)           # then fades

    def test_fermata_holds_the_event_and_moves_nothing_else(self):
        bank = {'e': _tone(EVENT_F, 0.3), 'n': _tone(440.0, 0.3)}
        events = [{'t': 0.5, 'sample': 'e', 'gain_db': 0}, {'t': 1.2, 'sample': 'n', 'gain_db': 0}]
        plain = _render([], events=events, bank=bank)
        y = _render([{'type': 'fermata', 't': 0.5, 'hold_s': 1.0}], events=events, bank=bank)
        self.assertGreater(_level(y, EVENT_F, 0.9, 1.3), 0.2)          # held past its end
        self.assertEqual(len(y), len(plain))
        self.assertAlmostEqual(_level(y, 440.0, 1.25, 1.45), _level(plain, 440.0, 1.25, 1.45), places=2)


class MixTargetTests(unittest.TestCase):

    def test_staccato_range_chops_on_a_grid(self):
        y = _render([{'type': 'staccato', 'target': 'mix', 'from': 1.0, 'to': 2.0,
                      'every_s': 0.25, 'keep_s': 0.1}], events=[], base=_tone(BASE_F, 3.0))
        for k in range(4):
            a = 1.0 + 0.25 * k
            self.assertGreater(_rms(y, a + 0.01, a + 0.08), 0.15)      # each pulse sounds
            self.assertLess(_rms(y, a + 0.12, a + 0.24), 1e-4)         # then silence
        self.assertGreater(_rms(y, 2.1, 2.9), 0.15)                    # untouched after

    def test_staccato_range_on_attacks_is_not_one_long_silence(self):
        # The old range staccato silenced the whole range. Now each detected
        # attack keeps its start.
        base = np.zeros((int(3.0 * SR), 1), np.float32)
        hit = _tone(BASE_F, 0.4)[:, 0] * np.exp(-np.arange(int(0.4 * SR)) / (0.15 * SR))
        for a in (0.5, 1.0, 1.5, 2.0):
            base[int(a * SR):int(a * SR) + len(hit), 0] += hit
        y = _render([{'type': 'staccato', 'target': 'mix', 'from': 0.4, 'to': 2.5, 'keep_s': 0.1}],
                    events=[], base=base)
        for a in (1.0, 1.5, 2.0):
            self.assertGreater(_rms(y, a, a + 0.05), 0.05)

    def test_accent_point_boosts_everything(self):
        y = _render([{'type': 'accent', 'target': 'mix', 't': 2.5}], events=[])
        plain = _render([], events=[])
        self.assertGreater(_rms(y, 2.5, 2.52) / _rms(plain, 2.5, 2.52), 1.6)

    def test_legato_carries_the_previous_sound_across(self):
        t = np.arange(int(2.0 * SR)) / SR
        base = (np.where(t < 1.0, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)) * 0.3)
        base = base.astype(np.float32)[:, None]
        y = _render([{'type': 'legato', 'target': 'mix', 't': 1.0}], events=[], base=base)
        self.assertGreater(_level(y, 220.0, 1.02, 1.1), 0.1)           # 220 Hz rings on
        self.assertLess(_level(base, 220.0, 1.02, 1.1), 0.01)

    def test_fermata_makes_the_whole_piece_wait(self):
        t = np.arange(int(3.0 * SR)) / SR
        base = (np.where(t < 1.5, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)) * 0.3)
        base = base.astype(np.float32)[:, None]
        score = {'articulations': [{'type': 'fermata', 'target': 'mix', 't': 1.0, 'hold_s': 1.0}]}
        mix, tmap = render_mix(score, {}, [], SR, base)
        self.assertAlmostEqual(len(mix) / SR, 4.0, places=2)              # 1 s longer
        self.assertGreater(_level(mix, 220.0, 1.2, 1.9), 0.2)            # 220 Hz held
        self.assertGreater(_level(mix, 330.0, 2.6, 3.4), 0.2)            # the change came 1 s late
        self.assertLess(_level(mix, 330.0, 1.6, 1.9), 0.02)
        self.assertIn((1.0, 1.0), [tuple(p) for p in tmap])               # cursor stops at 1.0 s...
        self.assertIn((1.0, 2.0), [tuple(p) for p in tmap])               # ...for 1 s of real time


if __name__ == '__main__':
    unittest.main()
