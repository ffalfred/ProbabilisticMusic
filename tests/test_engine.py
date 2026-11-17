"""Regression tests for the render engine.

Run from the repo root:  python -m unittest discover -s tests
Uses synthetic audio only; SoX/ffmpeg are not needed.
"""
import os
import sys
import shutil
import tempfile
import unittest

import numpy as np
import soundfile as sf

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, ROOT)

from src.parser        import resolve_score, seed_everything
from src.sample_engine import build_bank
from src.interpreter   import interpret, _sample_noise, _rw_step
from src.character     import D, RW_BUILTIN
from src.pitch         import apply_noterel_to_mix, resolve_event_pitch
from src.mixer         import mix_events, _apply_state_to_mix
from src.renderer      import render_mix

SR = 22050


def _config(seed=None):
    return {'engine': 'v2', 'seed': seed, 'v2': {
        'A1': 0.7, 'A2': 0.2,
        'Q_base': [0.5, 0.04, 40.0, 0.04, 0.04, 0.04, 4000.0, 0.05, 0.04, 0.05, 8.0, 1.0],
    }}


def _sine(freq, dur, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class EngineTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wav(self, name, audio):
        path = os.path.join(self.tmp, name)
        sf.write(path, audio, SR, subtype='FLOAT')
        return path

    def test_multitrack_loads_every_track(self):
        p1 = self._wav('t1.wav', np.full(SR, 0.1, np.float32))
        p2 = self._wav('t2.wav', np.full(SR, 0.5, np.float32))
        bank, _, base = build_bank({
            'tracks': [{'path': p1}, {'path': p2}],
            'samples': {'s0': {'from': 0, 'to': 0.1, 'track': 0},
                        's1': {'from': 0, 'to': 0.1, 'track': 1}},
        })
        self.assertAlmostEqual(float(base[100]), 0.6, places=4)
        self.assertAlmostEqual(float(bank['s0'][10]), 0.1, places=4)
        self.assertAlmostEqual(float(bank['s1'][10]), 0.5, places=4)

    def test_simultaneous_events_survive_interpreter(self):
        score = {
            'samples': {'a': {'from': 0, 'to': 0.5}},
            'events': [{'t': 1.0, 'sample': 'a'}, {'t': 1.0, 'sample': 'a', 'pitch': 7},
                       {'t': 1.0, 'sample': 'a', 'pitch': 4}, {'t': 2.0, 'sample': 'a'}],
            'dynamics': [{'t': 0, 'mark': 'p'}, {'t': 2, 'mark': 'f'}],
            'golems': [{'from': 0, 'to': 5, 'character': 'lyrical'}],
        }
        events = interpret(score, _config(seed=1))
        self.assertEqual(len(events), 4)
        self.assertEqual(sorted(e.get('pitch', 0) for e in events), [0, 0, 4, 7])

    def test_skew_normal_samples(self):
        x = _sample_noise(np.random.default_rng(0), D, 'skew_normal', np.ones(D), skew=3.0)
        self.assertEqual(np.shape(x), (D,))

    def test_random_walk_tolerates_short_vectors(self):
        char = dict(RW_BUILTIN['rw_free'])
        char['step_size'] = [1.0, 0.1, 5.0, 0.1, 0.1]          # 5-dim, as old UIs saved
        char['correlation'] = np.eye(5).tolist()
        x = _rw_step(np.zeros(D), char, np.random.default_rng(0))
        self.assertEqual(x.shape, (D,))

    def test_filter_cutoff_is_in_hz(self):
        score = {
            'samples': {'a': {'from': 0, 'to': 0.5}},
            'events': [{'t': 1.0, 'sample': 'a'}],
            'dynamics': [{'t': 0, 'mark': 'pp'}, {'t': 4, 'mark': 'ff'}],
            'golems': [{'from': 0, 'to': 8, 'character': 'lyrical'}],
        }
        _, trace = interpret(score, _config(seed=2), return_trace=True)
        cut = np.array([s['sample'][6] for s in trace])
        self.assertTrue(np.all(cut >= 1000.0), cut.min())
        # A trace sitting at 1 kHz must audibly darken an 8 kHz tone.
        tone = _sine(8000, 1.0)
        dark = [{'t': 0.0, 'sample': [0.0] * 6 + [1000.0, 0.0] + [0.0] * 4},
                {'t': 1.0, 'sample': [0.0] * 6 + [1000.0, 0.0] + [0.0] * 4}]
        out = _apply_state_to_mix(tone.copy(), SR, dark, ['filter_cutoff'])
        self.assertLess(np.sqrt(np.mean(out ** 2)), 0.2 * np.sqrt(np.mean(tone ** 2)))

    def test_brightness_does_not_hard_clip_the_mix(self):
        loud = _sine(6000, 1.0, amp=3.0)          # pre-normalisation mixes can exceed 1
        bright = [{'t': 0.0, 'sample': [0.0, 1.0] + [0.0] * 10},
                  {'t': 1.0, 'sample': [0.0, 1.0] + [0.0] * 10}]
        out = _apply_state_to_mix(loud, SR, bright, ['brightness'])
        self.assertGreater(float(np.max(np.abs(out))), 1.5)

    def test_glissando_shifts_events_once(self):
        nr = [{'type': 'glissando', 'from': 0.0, 'to': 2.0, 'from_pitch': 0, 'to_pitch': 4}]
        self.assertAlmostEqual(resolve_event_pitch(1.0, 0.0, nr), 2.0)
        # Full-band glissandi act on events only; the mix pass leaves the mix alone.
        mix = _sine(440, 2.0)
        self.assertTrue(np.array_equal(apply_noterel_to_mix(mix, SR, nr), mix))
        # Band-limited glissandi act on the mix, so events must not be shifted again.
        banded = [dict(nr[0], freq_from=200)]
        self.assertEqual(resolve_event_pitch(1.0, 0.0, banded), 0.0)
        self.assertFalse(np.allclose(apply_noterel_to_mix(mix, SR, banded), mix))

    def test_random_parameters_are_resolved(self):
        score = resolve_score({
            'samples': {'a': {'from': 0, 'to': 0.2}},
            'events': [{'t': 0.1, 'sample': 'a', 'speed': [0.5, 2.0],
                        'gain_db': {'distribution': 'gaussian', 'mean': -6, 'std': 1},
                        'reverse': {'distribution': 'bernoulli', 'p': 0.5}}],
            'dynamics': [{'t': 0, 'marking': 'mf'}],
        })
        ev = score['events'][0]
        self.assertIsInstance(ev['speed'], float)
        self.assertIsInstance(ev['gain_db'], float)
        self.assertIsInstance(ev['reverse'], bool)
        self.assertEqual(score['dynamics'][0]['mark'], 'mf')

    def _render(self, seed):
        base = self._wav('base.wav', _sine(330, 3.0))
        config = _config(seed=seed)
        seed_everything(config)
        score = resolve_score({
            'base_track': base,
            'samples': {'a': {'from': 0.0, 'to': 0.5}},
            'events': [{'t': 0.5, 'sample': 'a', 'speed': [0.8, 1.2], 'gain_db': [-9, -3],
                        'fx': [{'type': 'morpho_aleatoric', 'detune_cents': 40}]},
                       {'t': 1.5, 'sample': 'a'}],
            'dynamics': [{'t': 0, 'mark': 'p'}, {'t': 2, 'mark': 'f'}],
            'golems': [{'from': 0, 'to': 3, 'character': 'dramatic'}],
        })
        bank, sr, base_audio = build_bank(score)
        events, trace = interpret(score, config, return_trace=True)
        score['_state_trace'] = trace
        mix, _ = render_mix(score, bank, events, sr, base_audio)
        return mix

    def test_seed_reproduces_the_whole_render(self):
        a, b, c = self._render(7), self._render(7), self._render(8)
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))

    @unittest.skipUnless(shutil.which('sox'), 'SoX not installed')
    def test_sox_effects_are_deterministic_and_unclipped(self):
        from src.fx import apply_fx
        clip = _sine(220, 1.0)
        for fx in ({'type': 'reverb'}, {'type': 'eq', 'freq': 1000, 'gain': 0.1}):
            with self.subTest(fx=fx['type']):
                loud = apply_fx(clip * 5, SR, [fx])   # pre-normalisation level
                self.assertTrue(np.array_equal(loud, apply_fx(clip * 5, SR, [fx])))
                quiet = apply_fx(clip.copy(), SR, [fx])
                self.assertAlmostEqual(np.max(np.abs(loud)) / np.max(np.abs(quiet)), 5.0, places=2)

    def test_every_plugin_runs(self):
        from plugins import load_plugins, apply_plugin
        clip = _sine(220, 1.0) + _sine(1320, 1.0, amp=0.1)
        plugins = load_plugins()
        self.assertEqual(len(plugins), 20)
        for key in plugins:
            with self.subTest(plugin=key):
                out = apply_plugin(clip.copy(), SR, {'type': key})
                self.assertEqual(len(out), len(clip))
                self.assertTrue(np.all(np.isfinite(out)))

    def test_muted_events_do_not_duck(self):
        score = {'duck_base': {'enabled': True, 'amount_db': -20},
                 'samples': {'a': {'from': 0, 'to': 0.1}}}
        base = np.full(SR, 0.5, np.float32)
        bank = {'a': np.zeros(int(0.1 * SR), np.float32)}
        mix = mix_events([{'t': 0.5, 'sample': 'a', 'muted': True}], bank, SR, score, base)
        self.assertAlmostEqual(float(mix[int(0.52 * SR)]), 0.5, places=4)


if __name__ == '__main__':
    unittest.main()
