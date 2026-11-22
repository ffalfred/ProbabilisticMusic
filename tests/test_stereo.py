"""Stereo support: audio keeps its channels from loading to output.

Run from the repo root:  python -m unittest discover -s tests
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
from src.interpreter   import interpret
from src.renderer      import render_mix, _apply_phrase_tempo
from src.fx            import apply_fx

SR = 22050


def _sine(freq, dur, amp=0.3):
    t = np.arange(int(dur * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


class StereoTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _wav(self, name, audio):
        path = os.path.join(self.tmp, name)
        sf.write(path, audio, SR, subtype='FLOAT')
        return path

    def _render(self, score, golems=None, seed=1):
        config = {'engine': 'v2', 'seed': seed, 'v2': {
            'Q_base': [0.5, 0.04, 40.0, 0.04, 0.04, 0.04, 4000.0, 0.05, 0.04, 0.05, 8.0, 1.0]}}
        seed_everything(config)
        score = _apply_phrase_tempo(resolve_score(score))
        bank, sr, base = build_bank(score)
        if golems:
            score['golems'] = golems
            events, trace = interpret(score, config, return_trace=True)
            score['_state_trace'] = trace
        else:
            events = sorted(score['events'], key=lambda e: e['t'])
        mix, _ = render_mix(score, bank, events, sr, base)
        return mix, bank, base

    def test_hard_panned_source_stays_panned(self):
        left = _sine(330, 3.0)
        path = self._wav('lr.wav', np.stack([left, np.zeros_like(left)], axis=1))
        mix, bank, base = self._render({
            'base_track': path,
            'samples': {'a': {'from': 0.2, 'to': 0.7}},
            'events': [{'t': 1.0, 'sample': 'a', 'gain_db': 0, 'speed': 1.5, 'pitch': 3},
                       {'t': 1.0, 'sample': 'a', 'reverse': True, 'loop': 1}],
            'dynamics': [{'t': 0, 'mark': 'p'}, {'t': 2, 'mark': 'f'}],
            'mix_dims': ['gain_db', 'brightness', 'filter_cutoff'],
        }, golems=[{'from': 0, 'to': 3, 'character': 'dramatic'}])
        self.assertEqual(base.shape[1], 2)
        self.assertEqual(bank['a'].shape[1], 2)
        self.assertEqual(mix.ndim, 2)
        self.assertEqual(mix.shape[1], 2)
        self.assertGreater(_rms(mix[:, 0]), 0.05)
        self.assertLess(_rms(mix[:, 1]), 1e-4)       # nothing leaked into the right

    def test_mono_source_renders_mono(self):
        path = self._wav('m.wav', _sine(220, 2.0))
        mix, _, _ = self._render({'base_track': path,
                                  'samples': {'a': {'from': 0, 'to': 0.5}},
                                  'events': [{'t': 0.5, 'sample': 'a'}]})
        self.assertEqual(mix.shape[1], 1)

    def test_mono_and_stereo_tracks_mix_to_stereo(self):
        mono = self._wav('mono.wav', np.full(SR, 0.2, np.float32))
        st = self._wav('st.wav', np.stack([np.full(SR, 0.1, np.float32),
                                           np.full(SR, -0.1, np.float32)], axis=1))
        bank, _, base = build_bank({'tracks': [{'path': mono}, {'path': st}],
                                    'samples': {'m': {'from': 0, 'to': 0.1, 'track': 0}}})
        self.assertEqual(base.shape[1], 2)
        np.testing.assert_allclose(base[100], [0.3, 0.1], atol=1e-6)   # mono on both sides
        self.assertEqual(bank['m'].shape, (int(0.1 * SR), 2))

    def test_tracks_at_other_sample_rates_are_resampled(self):
        # base at SR (22.05 kHz); a stereo track at 44.1 kHz with a 1 kHz tone
        base = self._wav('base.wav', np.zeros(SR, np.float32))
        hi = os.path.join(self.tmp, 'hi.wav')
        t = np.arange(44100) / 44100
        sf.write(hi, np.stack([0.5 * np.sin(2 * np.pi * 1000 * t)] * 2, axis=1).astype(np.float32),
                 44100, subtype='FLOAT')
        bank, sr, mix = build_bank({'tracks': [{'path': base}, {'path': hi, 'fx': [{'type': 'tremolo', 'rate': 0.0001, 'depth': 0}]}],
                                    'samples': {'s': {'from': 0.2, 'to': 0.7, 'track': 1}}})
        self.assertEqual(sr, SR)
        self.assertEqual(len(mix), SR)                     # 1 s, not 2 s
        spectrum = np.abs(np.fft.rfft(mix[:, 0]))
        peak_hz = np.argmax(spectrum) * sr / len(mix)
        self.assertAlmostEqual(peak_hz, 1000, delta=2)     # pitch kept (was 500 Hz)
        self.assertEqual(len(bank['s']), int(0.7 * SR) - int(0.2 * SR))

    def test_every_effect_handles_stereo(self):
        from plugins import load_plugins
        # Identical channels must stay identical (same random draws per side);
        # silence on one side must stay silent for channel-separate effects.
        same = np.stack([_sine(220, 1.0)] * 2, axis=1)
        # Plugins with a `spread` setting place voices across the stereo
        # field on purpose; with spread 0 they must keep identical sides too.
        effects = [{'type': k, **({'spread': 0} if 'spread' in m.PARAMS else {})}
                   for k, m in load_plugins().items()] + [
            {'type': t} for t in ('delay', 'filter', 'chorus', 'tremolo',
                                  'spectral_inversion', 'overtones')]
        if shutil.which('sox'):
            effects += [{'type': t} for t in ('reverb', 'overdrive', 'flanger',
                                              'pitch', 'compress', 'eq')]
        for fx in effects:
            with self.subTest(fx=fx['type']):
                out = apply_fx(same.copy(), SR, [fx])
                self.assertEqual(out.ndim, 2)
                self.assertEqual(out.shape[1], 2)
                self.assertTrue(np.all(np.isfinite(out)))
                if fx['type'] in ('reverb', 'flanger'):
                    continue   # SoX spreads these across the channels on purpose
                np.testing.assert_allclose(out[:, 0], out[:, 1], atol=1e-5)

    def test_events_do_not_modify_the_sample_bank(self):
        # Fades/gain are applied in place; reusing a sample must not compound them.
        from src.mixer import mix_events
        bank = {'a': np.stack([_sine(220, 0.5), _sine(330, 0.5)], axis=1)}
        before = bank['a'].copy()
        mix = mix_events([{'t': 0.0, 'sample': 'a'}, {'t': 1.0, 'sample': 'a'}],
                         bank, SR, {'samples': {'a': {}}}, np.zeros((2 * SR, 2), np.float32))
        np.testing.assert_array_equal(bank['a'], before)
        n = len(before)
        np.testing.assert_array_equal(mix[:n], mix[SR:SR + n])   # both events identical

    def test_band_limited_fx_on_stereo(self):
        x = np.stack([_sine(220, 1.0), _sine(3000, 1.0)], axis=1)
        out = apply_fx(x, SR, [{'type': 'filter', 'cutoff': 500, 'filter_type': 'lp',
                                'freq_from': 1000}])
        self.assertEqual(out.shape[1], 2)
        # Left (220 Hz) is below the band: level kept (the crossover shifts
        # phase, so compare levels, not samples). Right (3 kHz) is inside the
        # band and low-passed at 500 Hz: strongly reduced.
        self.assertAlmostEqual(_rms(out[:, 0]) / _rms(x[:, 0]), 1.0, delta=0.05)
        self.assertLess(_rms(out[:, 1]), 0.1 * _rms(x[:, 1]))

    def test_every_score_feature_on_stereo(self):
        x = np.stack([_sine(330, 6.0), _sine(440, 6.0, amp=0.2)], axis=1)
        path = self._wav('st6.wav', x)
        mix, _, _ = self._render({
            'base_track': path,
            'samples': {'a': {'from': 0.2, 'to': 0.8}, 'b': {'from': 1.0, 'to': 1.5}},
            'events': [
                {'t': 0.5, 'sample': 'a', 'speeds': [0.5, 1.0, 2.0]},
                {'t': 1.0, 'sample': 'b', 'pitch_lock': True, 'speed': 0.8},
                {'t': 1.5, 'sample': 'a', 'mix_mode': 'sidechain', 'blend': 0.6},
                {'t': 2.0, 'sample': 'b', 'fx': [{'type': 'tremolo'}, {'type': 'morpho_aleatoric'}]},
                {'t': 2.5, 'sample': 'a', 'muted': True},
                {'t': 3.0, 'sample': 'b'}, {'t': 3.2, 'sample': 'a'},
            ],
            'dynamics': [{'t': 0, 'mark': 'pp'}, {'from': 0.5, 'to': 2.5, 'mark': 'crescendo'},
                         {'t': 2.5, 'mark': 'ff'}],
            'tempo': [{'from': 1.0, 'to': 2.0, 'factor': 1.3},
                      {'from': 4.0, 'to': 5.0, 'factor': 0.8, 'shape': 'step'}],
            'phrases': [{'from': 0, 'to': 3, 'gain_db': -2, 'fade_in': 0.1, 'tempo_factor': 1.1}],
            'base_fx': [{'type': 'filter', 'cutoff': 8000}],
            'fx_ranges': [{'from': 1.0, 'to': 2.0, 'fade': True, 'fx': [{'type': 'delay', 'time': 0.1}]},
                          {'from': 3.0, 'to': 3.5, 'fx': [{'type': 'tremolo'}]}],
            'articulations': [{'type': 'staccato', 't': 0.6}, {'type': 'accent', 't': 1.0},
                              {'type': 'legato', 'from': 2.0, 'to': 2.6},
                              {'type': 'fermata', 'from': 3.0, 'to': 3.4},
                              {'type': 'fermata', 'from': 4.0, 'to': 4.4, 'freq_from': 500}],
            'note_rel': [{'type': 'glissando', 'from': 0.5, 'to': 1.5, 'to_pitch': 2},
                         {'type': 'glissando', 'from': 2.0, 'to': 3.0, 'to_pitch': 3, 'freq_from': 300},
                         {'type': 'arpeggiate', 'from': 3.0, 'to': 3.3}],
            'duck_base': {'enabled': True, 'amount_db': -6},
            'duck_key': {'enabled': True, 'key': 'a', 'amount_db': -4},
            'auto_mix': {'enabled': True},
            'mix_dims': ['gain_db', 'brightness', 'filter_cutoff'],
        }, golems=[{'from': 0, 'to': 6, 'character': 'turbulent'}])
        self.assertEqual(mix.ndim, 2)
        self.assertEqual(mix.shape[1], 2)
        self.assertLess(mix.shape[0], 12 * SR)                # sane length (no n×n broadcast)
        self.assertTrue(np.all(np.isfinite(mix)))
        self.assertGreater(_rms(mix[:, 1]), 0.01)


if __name__ == '__main__':
    unittest.main()
