"""Morphogenics that were rewritten to do what their names say.

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

from plugins import load_plugins

SR = 22050
P = load_plugins()


def _harmonic(f0=220.0, dur=2.0, n=6, decay=0.0):
    t = np.arange(int(dur * SR)) / SR
    y = sum(np.sin(2 * np.pi * f0 * k * t + k) / k for k in range(1, n + 1)) * np.exp(-t * decay)
    return (0.15 * y).astype(np.float32)


def _peaks(y, n):
    """The n strongest spectral peaks of the middle second, in Hz, sorted."""
    seg = y[len(y) // 4: len(y) // 4 + SR]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    pk = np.flatnonzero((S[1:-1] > S[:-2]) & (S[1:-1] >= S[2:])) + 1
    return np.sort(f[pk[np.argsort(S[pk])[-n:]]])


def _run(key, x, **params):
    np.random.seed(0)
    return P[key].process(x.copy(), SR, {'dry_wet': 100, **params})


class SpectralTests(unittest.TestCase):

    def test_harmonic_stretch_moves_partial_n_to_f0_n_beta(self):
        y = _run('morpho_harmonic_stretch', _harmonic(), octave_ratio=2.2, pivot_hz=0)
        beta = np.log2(2.2)
        np.testing.assert_allclose(_peaks(y, 5), [220 * k ** beta for k in range(1, 6)], atol=3)

    def test_harmonic_stretch_ratio_two_is_unchanged(self):
        x = _harmonic()
        np.testing.assert_array_equal(_run('morpho_harmonic_stretch', x, octave_ratio=2.0), x)

    def test_inharmonic_shifts_every_partial_by_the_same_hz(self):
        y = _run('morpho_inharmonic', _harmonic(), shift_hz=100)
        np.testing.assert_allclose(_peaks(y, 5), [220 * k + 100 for k in range(1, 6)], atol=2)

    def test_freeze_attacks_holds_the_note_through_its_decay(self):
        x = _harmonic(decay=4.0)                     # dies away to -35 dB by 1 s
        y = _run('morpho_spectral_freeze', x, mode='attacks', n_partials=20)
        late = slice(int(1.2 * SR), int(1.8 * SR))
        rms = lambda s: np.sqrt(np.mean(s ** 2))
        self.assertGreater(rms(y[late]), 10 * rms(x[late]))        # held, > +20 dB
        self.assertAlmostEqual(_peaks(y[late], 1)[0], 220, delta=4)  # same pitch

    def test_freeze_follow_rate_zero_holds_the_first_moment(self):
        t = np.arange(2 * SR) / SR
        x = np.where(t < 1, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)).astype(np.float32) * 0.3
        y = _run('morpho_spectral_freeze', x, mode='follow', freeze_rate=0.0, n_partials=0)
        self.assertAlmostEqual(_peaks(y[int(1.3 * SR):], 1)[0], 220, delta=4)


class LineTests(unittest.TestCase):

    def test_endless_melody_never_drops_out(self):
        # Notes every 150 ms: the old version faded to silence at every one
        t = np.arange(3 * SR) / SR
        x = np.zeros_like(t)
        for i, a in enumerate(np.arange(0.1, 2.9, 0.15)):
            g = (t >= a) & (t < a + 0.15)
            x += g * np.sin(2 * np.pi * (220 + 20 * (i % 5)) * t) * 0.3
        x = x.astype(np.float32)
        y = _run('morpho_endless_melody', x, crossfade_ms=200)
        w = int(0.01 * SR)
        e = lambda s: np.sqrt(np.mean(s[:len(s) // w * w].reshape(-1, w) ** 2, axis=1))
        ex, ey = e(x)[15:-15], e(y)[15:-15]
        self.assertLess(np.mean(ey < ex * 0.25), 0.02)               # >12 dB drops: <2% of the time

    def test_endless_melody_carries_the_previous_note_across(self):
        t = np.arange(int(1.2 * SR)) / SR
        x = (np.where(t < 0.6, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)) * 0.3)
        x[t < 0.1] = 0
        x = x.astype(np.float32)
        y = _run('morpho_endless_melody', x, crossfade_ms=300)
        seg = y[int(0.62 * SR):int(0.75 * SR)]
        S = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        self.assertGreater(S[np.abs(f - 220) < 10].max(), 0.1 * S.max())   # 220 Hz rings on

    def test_tristan_voicing(self):
        mod = sys.modules[P['morpho_tristan_chord'].__name__]
        self.assertEqual(mod._VOICINGS['tristan'], [0.0, 6.0, 10.0, 15.0])

    def test_lyricism_intervals_and_placement(self):
        x = _harmonic(n=1)
        y = _run('morpho_lyricism', x, interval_1=12, interval_2=0, placement='below', harm_gain_db=-6)
        self.assertAlmostEqual(_peaks(y, 2)[0], 110, delta=3)        # an octave below added


class GrainAndGendyTests(unittest.TestCase):

    def test_grain_stream_without_randomness_is_the_input(self):
        x = _harmonic()
        y = _run('morpho_grain_scatter', x, pitch_spread=0, shuffle_pct=0, amplitude_var=0)
        np.testing.assert_allclose(y, x, atol=1e-6)

    def test_gendy_randomness_zero_is_the_input(self):
        x = _harmonic()
        for mode in ('input', 'envelope'):
            np.testing.assert_allclose(_run('morpho_gendy', x, mode=mode, randomness=0), x, atol=1e-6)

    def test_gendy_modes_are_reproducible(self):
        x = _harmonic()
        for mode in ('input', 'synth', 'envelope'):
            a = _run('morpho_gendy', x, mode=mode, randomness=60)
            b = _run('morpho_gendy', x, mode=mode, randomness=60)
            np.testing.assert_array_equal(a, b)
            self.assertTrue(np.isfinite(a).all())

    def test_gendy_input_and_envelope_are_click_free(self):
        # The old envelope jumped between levels every 20 ms (clicks). Now
        # breakpoints are joined by lines; the read head may run up to ~2x
        # (an octave up), which steepens the waveform but never steps it.
        x = _harmonic()
        max_jump = np.abs(np.diff(x)).max()
        for mode in ('input', 'envelope'):
            a = _run('morpho_gendy', x, mode=mode, randomness=60)
            self.assertLessEqual(np.abs(np.diff(a)).max(), max_jump * 2.5)

    def test_gendy_synth_sits_on_the_input_pitch(self):
        x = _harmonic(f0=220)
        y = _run('morpho_gendy', x, mode='synth', randomness=0, breakpoints=12)
        seg = y[SR // 2: SR // 2 + SR].astype(np.float64)
        # The waveform repeats every 1/220 s (its random shape may still give
        # it a strong 2nd harmonic, so test periodicity, not the peak)
        lag = round(SR / 220)
        a, b = seg[:-lag], seg[lag:]
        self.assertGreater(np.dot(a, b) / np.sqrt(np.dot(a, a) * np.dot(b, b)), 0.95)



class PitchCopyTests(unittest.TestCase):

    def test_undertones_are_exact(self):
        mod = sys.modules[P['morpho_undertones'].__name__]
        np.testing.assert_allclose(mod._UNDERTONE_STEPS, [12 * np.log2(n) for n in range(2, 9)])

    def test_microtonal_follows_brightness(self):
        t = np.arange(2 * SR) / SR
        dark = 0.3 * np.sin(2 * np.pi * 300 * t[:SR])
        bright = 0.15 * sum(np.sin(2 * np.pi * f * t[SR:]) for f in (300, 6000, 7000, 8000))
        y = _run('morpho_microtonal', np.concatenate([dark, bright]).astype(np.float32), max_cents=50)

        def partial(seg):
            S = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
            f = np.fft.rfftfreq(len(seg), 1 / SR)
            return f[np.argmax(S * ((f > 250) & (f < 350)))]
        self.assertLess(partial(y[int(0.3 * SR):int(0.9 * SR)]), 296)       # dark: flat
        self.assertGreater(partial(y[int(1.3 * SR):int(1.9 * SR)]), 304)    # bright: sharp


class PendereckiTests(unittest.TestCase):

    def test_band_has_every_step(self):
        from plugins import _cluster
        np.testing.assert_array_equal(_cluster.band(4, 'semitone'), [-2, -1, 0, 1, 2])
        np.testing.assert_array_equal(_cluster.band(2, 'quarter tone'), [-1, -0.5, 0, 0.5, 1])
        self.assertEqual(len(_cluster.band(24, 'quarter tone')), _cluster.MAX_VOICES)

    def test_cluster_contains_the_band(self):
        y = _run('morpho_cluster', _harmonic(n=1, dur=2.0), cluster_width=2, drift_cents=0)
        np.testing.assert_allclose(_peaks(y, 3), [220 * 2 ** (k / 12) for k in (-1, 0, 1)], atol=3)

    def test_cluster_entries_build_up(self):
        x = _harmonic(dur=3.0)
        y = _run('morpho_cluster', x, cluster_width=4, entry_s=2.0)
        rms = lambda s: np.sqrt(np.mean(s ** 2))
        self.assertLess(rms(y[int(0.05 * SR):int(0.25 * SR)]), 0.5 * rms(y[int(2.5 * SR):]))

    def test_textural_is_restless_and_reproducible(self):
        x = _harmonic(dur=2.0)
        a = _run('morpho_textural', x)
        b = _run('morpho_textural', x)
        np.testing.assert_array_equal(a, b)
        w = int(0.05 * SR)
        env = np.sqrt(np.mean(a[:len(a) // w * w].reshape(-1, w) ** 2, axis=1))[2:-2]
        self.assertGreater(env.std() / env.mean(), 0.05)          # it swells


class StereoTests(unittest.TestCase):

    def test_dual_mono_matches_mono(self):
        # Every plugin, given the same sound on both sides (and no spread),
        # returns that sound's mono result on both sides.
        from plugins import apply_plugin
        x = _harmonic(dur=1.0, decay=2.0)
        for key, mod in sorted(P.items()):
            fx = {'type': key}
            if 'spread' in mod.PARAMS:
                fx['spread'] = 0
            np.random.seed(5)
            m = apply_plugin(x[:, None], SR, fx)[:, 0]
            np.random.seed(5)
            s = apply_plugin(np.stack([x, x], axis=1), SR, fx)
            with self.subTest(key):
                np.testing.assert_allclose(s[:, 0], m, atol=1e-4)
                np.testing.assert_allclose(s[:, 1], m, atol=1e-4)

    def test_spread_widens_a_mono_sound(self):
        from plugins import apply_plugin
        x = _harmonic(dur=1.5)
        st = np.stack([x, x], axis=1)
        for key in ('morpho_cluster', 'morpho_textural', 'morpho_grain_scatter', 'morpho_gendy'):
            np.random.seed(0)
            y = apply_plugin(st, SR, {'type': key, 'spread': 100})
            side = np.sqrt(np.mean((y[:, 0] - y[:, 1]) ** 2))
            mid = np.sqrt(np.mean((y[:, 0] + y[:, 1]) ** 2))
            with self.subTest(key):
                self.assertGreater(side / mid, 0.1)                   # side above -20 dB

    def test_stereo_plugins_decide_once_for_both_sides(self):
        # Onsets come from the mono sum: a hit only on the left still cuts
        # the right channel at the same place (Minimalism quotes it on both).
        from plugins import apply_plugin
        t = np.arange(2 * SR) / SR
        right = (0.2 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
        left = right.copy()
        for a in (0.3, 0.8, 1.3):
            i = int(a * SR)
            left[i:i + 200] += np.random.default_rng(0).standard_normal(200).astype(np.float32)
        np.random.seed(0)
        y = apply_plugin(np.stack([left, right], axis=1), SR,
                         {'type': 'morpho_minimalism', 'nth_onset': 2, 'quote_interval': 12, 'dry_wet': 100})
        self.assertGreater(np.abs(y[:, 1] - right).max(), 0.05)        # right side changed too


if __name__ == '__main__':
    unittest.main()
