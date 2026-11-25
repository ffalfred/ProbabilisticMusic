"""Golem dimensions added in the audit: overdrive (drive), dynamic centre
(compressor) and per-event pitch deviation.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.golem_fx import saturate, compress
from src.mixer import _apply_state_to_mix, _event_clip, mix_events

SR = 44100
T = np.arange(SR * 2) / SR


def _sine(amp=0.5, f=220.0):
    return (amp * np.sin(2 * np.pi * f * T)).astype(np.float32)[:, None].repeat(2, 1)


def _harmonic_db(y, h=3, f=220.0):
    sp = np.abs(np.fft.rfft(y[:, 0]))
    fr = np.fft.rfftfreq(len(y), 1 / SR)
    return 20 * np.log10(sp[np.argmin(abs(fr - h * f))] / sp[np.argmin(abs(fr - f))])


def _trace(dim, value):
    s = [0, 0.5, 0, 0.5, 0.5, 0, 5000, 0, 0.5, 0, 0, -12]
    s[dim] = value
    return [{'t': t, 'sample': list(s)} for t in (0.0, 1.0, 2.0)]


class DriveTests(unittest.TestCase):

    def test_drive_zero_is_the_input(self):
        x = _sine()
        self.assertTrue(np.array_equal(saturate(x, SR, np.zeros(len(x))), x))

    def test_more_drive_more_harmonics_same_level(self):
        x = _sine()
        h = [_harmonic_db(saturate(x, SR, np.full(len(x), d))) for d in (0.15, 0.3, 1.0)]
        self.assertTrue(h[0] < h[1] < h[2], h)
        self.assertGreater(h[2], -15)
        y = saturate(x, SR, np.full(len(x), 0.3))
        self.assertLess(abs(20 * np.log10(np.sqrt((y ** 2).mean() / (x ** 2).mean()))), 1.0)

    def test_drive_mix_dim(self):
        x = _sine()
        y = _apply_state_to_mix(x.copy(), SR, _trace(9, 0.6), mix_dims=['overdrive_drive'])
        self.assertGreater(_harmonic_db(y), _harmonic_db(x) + 20)


class DynamicsTests(unittest.TestCase):

    def test_lower_centre_squeezes_the_dynamics(self):
        amp = np.where(T < 1, 0.8, 0.05).astype(np.float32)[:, None]
        x = _sine(1.0) * amp

        def rng(thr):
            y = compress(x, SR, np.full(len(x), thr))
            loud = np.abs(y[int(0.5 * SR):SR]).max()
            quiet = np.abs(y[int(1.5 * SR):]).max()
            return 20 * np.log10(loud / quiet)
        r0 = 20 * np.log10(0.8 / 0.05)
        self.assertLess(rng(-6), r0)
        self.assertLess(rng(-18), rng(-6) - 4)

    def test_dynamics_mix_dim(self):
        x = _sine(0.9)
        y = _apply_state_to_mix(x.copy(), SR, _trace(11, -20.0), mix_dims=['dynamic_center'])
        self.assertLess(np.abs(y[SR:]).max(), 0.9 * 0.75)


class PitchTests(unittest.TestCase):

    def _pitch_of(self, clip):
        sp = np.abs(np.fft.rfft(clip[:, 0] * np.hanning(len(clip))))
        fr = np.fft.rfftfreq(len(clip), 1 / SR)
        return fr[np.argmax(sp)]

    def test_event_is_sharp_or_flat_by_its_cents(self):
        tone = _sine(0.5, 440.0)
        for lock in (False, True):
            ev = {'t': 0, 'sample': 'a', 'gain_db': 0.0, 'pitch_dev_cents': 40.0, 'pitch_lock': lock}
            f = self._pitch_of(_event_clip(ev, tone, SR, 2, None, None, {}, None))
            with self.subTest(pitch_lock=lock):
                self.assertAlmostEqual(1200 * np.log2(f / 440.0), 40.0, delta=6)

    def test_pitch_only_with_its_mix_dim(self):
        tone = _sine(0.5, 440.0)
        ev = [{'t': 0.0, 'sample': 'a', 'gain_db': 0.0, 'pitch_dev_cents': 40.0}]
        score = {'golems': [{'from': 0, 'to': 2}], 'mix_dims': []}
        off = mix_events(ev, {'a': tone}, SR, dict(score))
        on = mix_events(ev, {'a': tone}, SR, dict(score, mix_dims=['pitch_dev_cents']))
        self.assertAlmostEqual(self._pitch_of(off[:SR]), 440.0, delta=2)
        self.assertGreater(self._pitch_of(on[:SR]), 447.0)          # +40 cents = 450.3 Hz



class TempoTests(unittest.TestCase):

    DYN = [{'t': 0, 'marking': 'p'}, {'from': 6, 'to': 12, 'marking': 'crescendo'}, {'t': 14, 'marking': 'f'},
           {'from': 18, 'to': 24, 'marking': 'decrescendo'}, {'t': 26, 'marking': 'p'}]
    EVS = [{'t': float(t), 'sample': 'a'} for t in np.arange(0.5, 30, 0.25)]

    def _trace(self, ch, seed=3, **score):
        import yaml
        from src.interpreter import interpret
        with open(os.path.join(os.path.dirname(__file__), '..', 'config.yaml')) as f:
            cfg = yaml.safe_load(f)
        sc = dict({'events': self.EVS, 'dynamics': self.DYN, 'phrases': [{'from': 0, 'to': 15}],
                   'golems': [{'from': 0, 'to': 30, 'character': ch}]}, **score)
        evs, tr = interpret(sc, {'v2': dict(cfg['v2'], seed=seed)}, return_trace=True)
        return evs, tr

    def test_rubato_presses_and_broadens(self):
        _, tr = self._trace('lyrical')
        T = np.array([s['t'] for s in tr])
        X = np.array([s['sample'][12] for s in tr])
        seg = lambda a, b: X[(T >= a) & (T < b)].mean()
        self.assertGreater(seg(8, 12), seg(1, 5) + 1.5)          # crescendo: forward
        self.assertLess(seg(14.5, 15), seg(1, 5) - 4)            # phrase end: broader
        self.assertLess(seg(19, 23), seg(1, 5) - 1.5)            # decrescendo: back

    def test_disciplined_is_nearly_strict(self):
        X = np.array([s['sample'][12] for s in self._trace('disciplined')[1]])
        Y = np.array([s['sample'][12] for s in self._trace('lyrical')[1]])
        self.assertLess(X.std(), 0.5 * Y.std())

    def test_tempo_mix_dim_stretches_and_maps_time(self):
        from src.renderer import render_mix
        evs, tr = self._trace('lyrical')
        bank = {'a': (0.3 * np.sin(2 * np.pi * 440 * np.arange(int(0.2 * SR)) / SR)).astype(np.float32)[:, None]}
        base = {'golems': [{'from': 0, 'to': 30, 'character': 'lyrical'}], '_state_trace': tr,
                'dynamics': self.DYN, 'phrases': [{'from': 0, 'to': 15}]}
        off, m0 = render_mix(dict(base, mix_dims=[]), bank, evs, SR)
        on, m1 = render_mix(dict(base, mix_dims=['tempo']), bank, evs, SR)
        self.assertNotEqual(len(on), len(off))
        self.assertAlmostEqual(m1[-1][1], len(on) / SR, delta=0.01)          # map matches the audio
        # the phrase end (score 15 s) is reached later than written: it broadened
        from src.renderer import _score_to_real
        self.assertGreater(_score_to_real(15.0, m1) - _score_to_real(13.0, m1), 2.0)

    def test_golems_saved_with_12_dims_still_work(self):
        g = {'from': 0, 'to': 30, 'character': 'custom', 'A1_dims': [0.7] * 12, 'A2_dims': [0.2] * 12,
             'Q_base': [0.5, 0.04, 40, 0.04, 0.04, 0.04, 4000, 0.05, 0.04, 0.05, 8, 1], 'fp_mask': [1] * 12,
             'dist_config': {'dist_dims': [''] * 12}}
        rw = {'from': 0, 'to': 30, 'type': 'random_walk', 'character': 'custom',
              'step_size': [1.5, 0.05, 20, 0.05, 0.05, 0.05, 200, 0.05, 0.05, 0.05, 5, 1],
              'drift': [0] * 12, 'mr_dims': [0.1] * 12, 'correlation': np.eye(12).tolist()}
        for golem in (g, rw):
            evs, tr = self._trace('x', golems=[golem])
            self.assertEqual(len(tr[0]['sample']), 13)


if __name__ == '__main__':
    unittest.main()
