"""A saturated channel must not produce an amplitude.

WHY THIS EXISTS
---------------
RV5 and SV1 feed Sokolow-Lyon, which calls left ventricular hypertrophy at
RV5 + SV1 >= 35 mm. Both are read off leads that this hardware can saturate.

The 12-bit converter reaches +/-2048 counts from mid-rail, which at the bench-
measured 1423 counts/mV is +/-1.44 mV, against the +/-5 mV IEC 60601-2-25 asks
for. That is not a theoretical margin: on one ordinary 12-lead recording from this
device, SIX of the eight acquisition channels touched a rail.

A clipped peak reads LOWER than the true one. So a railed lead does not give an
underestimate of a large R wave - it gives a number with no relationship to the
patient, and one that looks entirely plausible on the page. Refusing is the only
honest answer, and the report already prints "--" for an unmeasured value.

Run:
    python -m unittest tests.test_amplitude_saturation -v
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from ecg.clinical_measurements import measure_rv5_sv1_from_median_beat  # noqa: E402
from ecg.calibration import ADC_PER_MV, FULL_SCALE_MV                   # noqa: E402
from ecg.arrhythmia_detector import detect_r_peaks_pan_tompkins         # noqa: E402

FS = 500.0
MID = 2048


def _beats(r_amp, s_amp, n_sec=12.0, rr=0.85):
    """A V-lead-shaped train: R then S, centred on mid-rail."""
    t = np.arange(int(n_sec * FS)) / FS
    b = t % rr
    x = (MID
         + r_amp * np.exp(-((b - 0.40) ** 2) / (2 * 0.008 ** 2))
         + s_amp * np.exp(-((b - 0.425) ** 2) / (2 * 0.010 ** 2)))
    return x


def _peaks(x):
    return np.asarray(detect_r_peaks_pan_tompkins(x, FS), dtype=int)


class TestRailedLeadsRefuse(unittest.TestCase):

    def test_a_clean_pair_measures(self):
        """The guard must not swallow a normal recording."""
        v5, v1 = _beats(900, -150), _beats(200, -700)
        rv5, sv1 = measure_rv5_sv1_from_median_beat(v5, v1, _peaks(v5), _peaks(v1), FS)
        self.assertIsNotNone(rv5, "a clean V5 produced no RV5")
        self.assertIsNotNone(sv1, "a clean V1 produced no SV1")
        self.assertGreater(rv5, 0.0)
        self.assertLess(sv1, 0.0)

    def test_a_railed_v5_gives_no_rv5(self):
        v5 = np.clip(_beats(2600, -150), 0, 4095)      # R drives past the top rail
        v1 = _beats(200, -700)
        self.assertGreaterEqual(v5.max(), 4090, "test signal did not actually clip")
        rv5, sv1 = measure_rv5_sv1_from_median_beat(v5, v1, _peaks(v5), _peaks(v1), FS)
        self.assertIsNone(rv5, "RV5 was reported from a saturated V5")
        self.assertIsNotNone(sv1, "a clean V1 should still give SV1")

    def test_a_railed_v1_gives_no_sv1(self):
        v5 = _beats(900, -150)
        v1 = np.clip(_beats(200, -2400), 0, 4095)      # S drives past the bottom rail
        self.assertLessEqual(v1.min(), 5, "test signal did not actually clip")
        rv5, sv1 = measure_rv5_sv1_from_median_beat(v5, v1, _peaks(v5), _peaks(v1), FS)
        self.assertIsNone(sv1, "SV1 was reported from a saturated V1")
        self.assertIsNotNone(rv5, "a clean V5 should still give RV5")

    def test_near_rail_counts_as_saturated(self):
        """An amplifier compresses as it approaches the limit; it does not clip
        cleanly at one count. A lead whose minimum is 2 is saturated in practice,
        and a real recording from this device had exactly that."""
        v5 = _beats(900, -150)
        v1 = np.clip(_beats(200, -2400), 2, 4095)
        self.assertEqual(v1.min(), 2)
        _, sv1 = measure_rv5_sv1_from_median_beat(v5, v1, _peaks(v5), _peaks(v1), FS)
        self.assertIsNone(sv1, "a lead sitting 2 counts off the rail was measured")


class TestTheCeilingIsRecorded(unittest.TestCase):
    """Sokolow-Lyon asks for an amplitude this hardware cannot reach."""

    def test_sokolow_threshold_exceeds_what_two_channels_can_carry(self):
        ceiling_mv = 2 * FULL_SCALE_MV          # RV5 and SV1 saturate independently
        self.assertLess(
            ceiling_mv, 3.5,
            "the hardware can now reach the 3.5 mV Sokolow-Lyon threshold — "
            "revisit docs/BENCH_RESULTS_2026-08-31.md and the LVH work that was "
            "stopped because it could not")
        self.assertAlmostEqual(ADC_PER_MV, 1423.0, places=1)
