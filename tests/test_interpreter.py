"""Interpreter (golems / Kalman engine): the Phase-1 audit fixes.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest
import warnings

import numpy as np
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)
warnings.filterwarnings('ignore')

import src.interpreter as I
from src.interpreter import interpret
from src.character import BUILTIN, RW_BUILTIN, character_at, DIM_NAMES
from src.envelope import DYNAMIC_LEVELS

CFG = yaml.safe_load(open(os.path.join(ROOT, 'config.yaml')))
DIM = {n: i for i, n in enumerate(DIM_NAMES)}


def _run(golems, dynamics, dur=40.0, seed=3, events=True, **v2):
    evs = [{'t': float(t), 'sample': 'a'} for t in np.arange(0.5, dur, 0.5)] if events else []
    cfg = {'v2': dict(CFG.get('v2', {}), seed=seed, **v2)}
    _, tr = interpret({'events': evs, 'dynamics': dynamics, 'golems': golems}, cfg, return_trace=True)
    return np.array([s['t'] for s in tr]), np.array([s['sample'] for s in tr]), np.array([s['mu'] for s in tr])


MARKS = [{'t': 0, 'marking': 'p'}, {'t': 10, 'marking': 'mf'}, {'t': 20, 'marking': 'ff'}, {'t': 30, 'marking': 'pp'}]


class HomeValueTests(unittest.TestCase):

    def test_nothing_drifts_to_zero_without_a_golem_or_for_any_preset(self):
        # Width used to sink to ~0.09 (nearly mono) with no golem or the six
        # editor-only presets
        for ch in (None, 'disciplined', 'impressionist', 'impulsive', 'volatile', 'sight_reading', 'memorised'):
            g = [] if ch is None else [{'from': 0, 'to': 40, 'character': ch}]
            _, S, _ = _run(g, MARKS)
            with self.subTest(ch):
                self.assertGreater(S[10:, DIM['stereo_width']].mean(), 0.35)
                self.assertGreater(S[10:, DIM['filter_cutoff']].mean(), 1500)

    def test_each_character_rests_at_its_own_width(self):
        widths = {ch: _run([{'from': 0, 'to': 40, 'character': ch}], MARKS)[1][10:, DIM['stereo_width']].mean()
                  for ch in ('sparse', 'impressionist')}
        self.assertLess(widths['sparse'], 0.45)
        self.assertGreater(widths['impressionist'], 0.6)


class GainTests(unittest.TestCase):

    def test_gain_follows_the_markings(self):
        # Soft dynamics used to come out 2–6 dB too loud
        for ch in ('lyrical', 'dramatic', 'sparse'):
            T, _, M = _run([{'from': 0, 'to': 40, 'character': ch}], MARKS)
            for d, t1 in zip(MARKS, (10, 20, 30, 40)):
                sel = (T >= d['t'] + 4) & (T < t1 - 3.5)          # mid-section, away from transitions
                err = M[sel, 0].mean() - 20 * np.log10(DYNAMIC_LEVELS[d['marking']])
                with self.subTest(ch=ch, marking=d['marking']):
                    self.assertLess(abs(err), 1.5)

    def test_subito_and_accent_markings_set_their_levels(self):
        # subito_p used to make golems play mezzo-forte (unknown marking → mf)
        dyn = [{'t': 0, 'marking': 'f'}, {'t': 10, 'marking': 'subito_p'}, {'t': 20, 'marking': 'sfz'}]
        T, _, M = _run([{'from': 0, 'to': 30, 'character': 'sparse'}], dyn, dur=30)
        f = M[(T >= 4) & (T < 9), 0].mean()
        p = M[(T >= 14) & (T < 19), 0].mean()
        after_sfz = M[(T >= 24) & (T < 29), 0].mean()
        self.assertLess(p, f - 8)
        self.assertLess(abs(after_sfz - p), 3)            # sfz is an accent, not a new level

    def test_hairpins_are_followed(self):
        dyn = [{'t': 0, 'marking': 'p'}, {'from': 5, 'to': 15, 'marking': 'crescendo'}, {'t': 20, 'marking': 'f'}]
        T, _, M = _run([{'from': 0, 'to': 30, 'character': 'sparse'}], dyn, dur=30)
        g = [M[np.argmin(abs(T - t)), 0] for t in (4, 8, 11, 14, 17)]
        self.assertTrue(all(b > a for a, b in zip(g, g[1:])), g)          # rises through the hairpin
        self.assertGreater(g[-1], g[0] + 8)


class ScopeTests(unittest.TestCase):

    def test_golems_run_without_events(self):
        T, S, _ = _run([{'from': 0, 'to': 10, 'character': 'lyrical'}], MARKS[:2], dur=10, events=False)
        self.assertGreater(len(T), 5)

    def test_presets_are_defined_once(self):
        self.assertEqual(len(BUILTIN), 10)
        self.assertEqual(len(RW_BUILTIN), 9)
        for name, c in BUILTIN.items():
            with self.subTest(name):
                self.assertEqual(set(c['cold_start_bias']), set(DIM_NAMES))

    def test_reverting_walk_returns_home_not_to_zero(self):
        # rw_reverting used to pull the filter cutoff to 20 Hz
        _, S, _ = _run([{'from': 0, 'to': 40, 'type': 'random_walk', 'character': 'rw_reverting'}], MARKS)
        self.assertGreater(S[20:, DIM['filter_cutoff']].mean(), 1000)


class BlendingTests(unittest.TestCase):

    def test_inline_settings_are_blended_not_replaced(self):
        golems = [{'from': 0, 'to': 10, 'character': 'lyrical', 'A1': 0.2},
                  {'from': 0, 'to': 10, 'character': 'lyrical', 'A1': 0.8}]
        c = character_at(5.0, golems, 10.0)
        self.assertAlmostEqual(c['A1_dims'][0], 0.5, places=6)

    def test_editor_distribution_name_is_used(self):
        c = character_at(1.0, [{'from': 0, 'to': 10, 'character': 'lyrical', 'distribution': 'cauchy'}], 10.0)
        self.assertEqual(c['sample_dist'], 'cauchy')

    def test_per_golem_lambda_changes_the_performance(self):
        g = lambda lam: [{'from': 0, 'to': 40, 'character': 'lyrical', 'lam': lam, 'xi_regime': 2.0}]
        _, _, a = _run(g(0.1), MARKS)
        _, _, b = _run(g(0.95), MARKS)
        self.assertFalse(np.allclose(a[:, 0], b[:, 0]))

    def test_transition_lead_is_used(self):
        # Editor golems are character 'custom'; their transition settings must
        # reach the engine (step = no move before the marking)
        g = lambda **k: [{'from': 0, 'to': 20, 'character': 'custom', 'A1': 0.7, 'A2': 0.2, **k}]
        dyn = [{'t': 0, 'marking': 'pp'}, {'t': 15, 'marking': 'ff'}]
        T, _, early = _run(g(transition_blend=1.0, transition_shape='ramp'), dyn, dur=20)
        _, _, late = _run(g(transition_blend=0.0, transition_shape='step'), dyn, dur=20)
        sel = (T > 13.0) & (T < 14.8)
        self.assertGreater(early[sel, 0].mean(), late[sel, 0].mean() + 3)

    def test_blank_per_dim_distribution_follows_the_golem(self):
        seen = []
        orig = I._sample_noise
        def spy(rng, size, dist, *a, **k):
            seen.append(dist)
            return orig(rng, size, dist, *a, **k)
        I._sample_noise = spy
        try:
            I._sample_posterior(np.random.default_rng(0), np.zeros(I.D), np.eye(I.D), 'cauchy', 0.05, 4.0,
                                dist_dims=[''] * I.D)
        finally:
            I._sample_noise = orig
        self.assertEqual(set(seen), {'cauchy'})



class PerEventDimTests(unittest.TestCase):

    def _clip(self, **ev):
        from src.mixer import _event_clip
        tone = np.ones((44100, 1), dtype=np.float32)
        e = dict({'t': 0, 'sample': 'a', 'gain_db': 0.0, 'fade_in': 0.2, 'fade_out': 0.2}, **ev)
        return _event_clip(e, tone, 44100, 1, None, None, {}, None)[:, 0]

    def test_attack_shape_bends_the_fade_in(self):
        # Same fade length (shape 0.5 → ×1); compare the curve: a sharp attack
        # is louder early in the fade, a soft one quieter
        neutral = self._clip(attack_shape=0.5)
        sharp = self._clip(attack_shape=0.3)
        soft = self._clip(attack_shape=0.7)
        n_s, n_f = int(44100 * 0.2 * 0.6), int(44100 * 0.2 * 1.4)
        self.assertGreater(sharp[n_s // 2], neutral[n_s // 2])
        self.assertLess(soft[n_f // 4], neutral[n_f // 4])

    def test_release_shape_bends_the_fade_out(self):
        held = self._clip(release_shape=0.25)
        tail = self._clip(release_shape=0.75)
        # 50 ms before the end: a held release is still loud, a decaying one quiet
        i = -int(0.05 * 44100)
        self.assertGreater(held[i], 2 * tail[i])

    def test_timing_is_audible_and_follows_the_character(self):
        def spread(ch):
            evs = [{'t': float(t), 'sample': 'a'} for t in np.arange(0.5, 40, 0.25)]
            out = interpret({'events': evs, 'dynamics': MARKS, 'golems': [{'from': 0, 'to': 40, 'character': ch}]},
                            {'v2': dict(CFG.get('v2', {}), seed=4)})
            return np.std([e['timing_offset_ms'] for e in out])
        tight, loose, mid = spread('disciplined'), spread('impulsive'), spread('lyrical')
        self.assertLess(tight, 12)
        self.assertGreater(loose, 1.6 * tight)
        self.assertTrue(10 < mid < 25, mid)                  # around the ~10–20 ms that is heard

    def test_neutral_shape_is_unchanged(self):
        self.assertTrue(np.allclose(self._clip(attack_shape=0.5, release_shape=0.5), self._clip()))


if __name__ == '__main__':
    unittest.main()
