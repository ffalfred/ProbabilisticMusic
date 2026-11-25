"""The resonant filter (src/resfilter.py) and where it is used: the golems'
filter_cutoff / filter_resonance mix dims and the Composer's filter effect.

Run from the repo root:  python -m unittest discover -s tests
"""
import os
import sys
import unittest

import numpy as np
from scipy.signal import butter, sosfilt, sosfreqz

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.resfilter import resonant_filter, resonance_to_q, _sos
from src.mixer import _apply_state_to_mix
from src.fx import _filter

SR = 44100


def _noise(sec=2.0, ch=2):
    return (np.random.default_rng(1).standard_normal((int(SR * sec), ch)) * 0.1).astype(np.float32)


def _gain_db_at(sos, f):
    _, h = sosfreqz(sos, worN=[f], fs=SR)
    return 20 * np.log10(abs(h[0]))


class FilterTests(unittest.TestCase):

    def test_no_resonance_is_the_old_butterworth(self):
        x = _noise()
        for bt in ('low', 'high'):
            ref = sosfilt(butter(2, 1500, btype=bt, fs=SR, output='sos'), x, axis=0)
            self.assertLess(np.abs(resonant_filter(x, SR, 1500.0, 0.0, bt) - ref).max(), 1e-5)

    def test_resonance_makes_a_peak_at_the_cutoff(self):
        self.assertAlmostEqual(_gain_db_at(_sos(1000, resonance_to_q(0.0), SR, 'low'), 1000), -3.0, delta=0.1)
        self.assertGreater(_gain_db_at(_sos(1000, resonance_to_q(0.5), SR, 'low'), 1000), 8)
        self.assertGreater(_gain_db_at(_sos(1000, resonance_to_q(1.0), SR, 'low'), 1000), 20)

    def test_composer_filter_resonance_is_heard(self):
        x = _noise()
        flat = _filter(x, SR, {'cutoff': 1000, 'resonance': 0.0, 'filter_type': 'lp'})
        peak = _filter(x, SR, {'cutoff': 1000, 'resonance': 0.8, 'filter_type': 'lp'})
        self.assertGreater(np.sqrt((peak ** 2).mean()), 1.5 * np.sqrt((flat ** 2).mean()))

    def test_golem_filter_sweeps_smoothly(self):
        # Cutoff glides 300 Hz → 6 kHz. The output's median frequency (per
        # 50 ms) should rise steadily on a log scale. It used to jump in 16
        # steps; measured deviation was 0.16, now 0.075.
        x = _noise(8.0)
        trace = [{'t': t, 'sample': [0, 0.5, 0, 0, 0, 0, 300 * 20 ** (t / 8), 0.2, 0.5, 0, 0, 0]}
                 for t in np.arange(0, 8.01, 0.05)]
        y = _apply_state_to_mix(x.copy(), SR, trace, mix_dims=['filter_cutoff'])
        win, med = SR // 20, []
        f = np.fft.rfftfreq(win, 1 / SR)
        for s in range(0, len(y) - win, win):
            c = np.cumsum(np.abs(np.fft.rfft(y[s:s + win, 0])) ** 2)
            med.append(f[np.searchsorted(c, 0.5 * c[-1])])
        e = np.log(med)
        t = np.arange(len(e))
        resid = e - np.polyval(np.polyfit(t, e, 1), t)
        self.assertGreater(med[-1], 4 * med[0])
        self.assertLess(np.abs(np.convolve(resid, np.ones(5) / 5, 'valid')).max(), 0.11)


if __name__ == '__main__':
    unittest.main()
