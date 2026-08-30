"""J-point and QRS-amplitude regression suite for the muscle filter.

WHAT THIS PINS
--------------
A lead too noisy to hand the QRS back untouched used to fall all the way back to
the plain low-pass, which ran the selected cutoff straight across the complex.
Measured on recordings/raw_all_leads_20260827_120820.csv at the 25 Hz setting
that pulled the J point down by 0.54-1.12 mm in V1-V6 (worst V3) while the clean
limb leads on the same recording moved 0.000 mm, and cost 20-29% of the QRS
peak-to-peak in those same leads.

Why that matters more than the millimetres suggest: the gate is decided per lead
from that lead's own noise, and the chest leads are the noisy ones far more often
than the limb leads are. So the artifact is not spread evenly across the page --
it lands on V1-V6 and leaves I-aVF clean, which is the shape of a regional
finding. A J-point depression confined to the anterior leads reads as ischaemia.

The fix (EMG_GATE_FALLBACK_HZ) protects the QRS either way; what the noise level
decides is what it is protected WITH -- the untouched trace on a clean lead, a
wide-cutoff version on a noisy one.

Run:
    python -m unittest tests.test_filters_jpoint -v
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import ecg.ecg_filters as F                                  # noqa: E402
from ecg.ecg_filters import apply_emg_filter, lead_noise_ratio  # noqa: E402

FS = 500.0
ADC_PER_MV = 1184.0
MM_PER_MV = 10.0          # the report's gain, so tolerances read as millimetres
R_TO_J_MS = 40.0          # where the J point sits on the beats built below


def _beat_train(secs=10.0, hr=60.0, r_mv=1.5, s_mv=-0.9, noise_uv=0.0, seed=0):
    """A beat with a deep, SHARP S wave - the morphology the smearing acts on.

    A gaussian-only QRS is too smooth to show the effect: its energy is already
    below 25 Hz, so a 25 Hz low-pass barely touches it. Real S waves come back to
    baseline in ~15 ms, which is faster than a 25 Hz filter can follow.
    """
    n = int(secs * FS)
    t = np.arange(n) / FS
    x = np.zeros(n)
    rr = 60.0 / hr
    for k in range(int(secs / rr)):
        c = k * rr + 0.5
        x += 0.15 * np.exp(-((t - (c - 0.16)) ** 2) / (2 * 0.025 ** 2))     # P
        x += -0.10 * np.exp(-((t - (c - 0.020)) ** 2) / (2 * 0.006 ** 2))   # Q
        x += r_mv * np.exp(-((t - c) ** 2) / (2 * 0.008 ** 2))              # R
        x += s_mv * np.exp(-((t - (c + 0.022)) ** 2) / (2 * 0.007 ** 2))    # S
        x += 0.35 * np.exp(-((t - (c + 0.30)) ** 2) / (2 * 0.06 ** 2))      # T
    if noise_uv:
        x = x + np.random.default_rng(seed).normal(0, noise_uv / 1000.0, n)
    return t, x * ADC_PER_MV


def _r_peaks(sig):
    from scipy.signal import butter, filtfilt, find_peaks
    b, a = butter(2, [5 / (FS / 2), 35 / (FS / 2)], btype="band")
    ref = filtfilt(b, a, sig - np.mean(sig))
    pk, _ = find_peaks(np.abs(ref), height=np.percentile(np.abs(ref), 99) * 0.5,
                       distance=int(0.25 * FS))
    return pk[(pk > int(0.35 * FS)) & (pk < len(sig) - int(0.45 * FS))]


def _j_mm(sig, pk):
    """J-point level in mm, referenced to each beat's own PQ segment."""
    k = int(R_TO_J_MS / 1000 * FS)
    vals = [(sig[p + k] - np.mean(sig[p - int(0.08 * FS):p - int(0.06 * FS)])) / ADC_PER_MV * MM_PER_MV
            for p in pk]
    return float(np.median(vals))


def _qrs_pp_mm(sig, pk):
    w = [sig[p - int(0.05 * FS):p + int(0.06 * FS)] for p in pk]
    return float(np.median([(s.max() - s.min()) / ADC_PER_MV * MM_PER_MV for s in w]))


class TestNoisyLeadKeepsItsJPoint(unittest.TestCase):
    """The case that produced the field artifact: a lead above the gate limit."""

    def setUp(self):
        # 40 uV rms puts the ratio well over EMG_GATE_NOISE_LIMIT, so the gate
        # takes the fallback path - the path this suite exists to constrain.
        _, self.sig = _beat_train(noise_uv=40.0, seed=7)
        self.pk = _r_peaks(self.sig)
        self.assertGreaterEqual(len(self.pk), 5, "fixture must produce beats to measure")
        self.ratio = lead_noise_ratio(self.sig, FS)
        self.assertGreater(self.ratio, F.EMG_GATE_NOISE_LIMIT,
                           "fixture must be noisy enough to take the fallback path")
        self.j_raw = _j_mm(self.sig, self.pk)
        self.pp_raw = _qrs_pp_mm(self.sig, self.pk)

    def test_j_point_does_not_move_a_clinically_read_amount(self):
        """1 mm of ST/J shift is read as a finding. Stay well under half of it."""
        for setting in ("25", "35", "40", "150"):
            with self.subTest(setting=setting):
                y = apply_emg_filter(self.sig.copy(), FS, setting)
                shift = abs(_j_mm(y, self.pk) - self.j_raw)
                self.assertLess(shift, 0.5,
                                f"EMG {setting} Hz moved the J point {shift:.3f} mm on a "
                                f"noisy lead (was up to 1.12 mm before the fallback fix)")

    def test_qrs_amplitude_survives(self):
        """20-29% loss in V1-V6 was enough to change Sokolow-Lyon voltage."""
        for setting in ("25", "35", "40", "150"):
            with self.subTest(setting=setting):
                y = apply_emg_filter(self.sig.copy(), FS, setting)
                kept = _qrs_pp_mm(y, self.pk) / self.pp_raw
                self.assertGreater(kept, 0.90,
                                   f"EMG {setting} Hz kept only {kept*100:.1f}% of the QRS")

    def test_fallback_beats_the_plain_lowpass_it_replaced(self):
        """The gated path must be closer to raw than the old behaviour was.

        EMG_QRS_GATED=False reproduces exactly what a noisy lead used to get, so
        this compares the fix against the defect rather than against a constant.
        """
        for setting in ("25", "35", "40"):
            with self.subTest(setting=setting):
                fixed = apply_emg_filter(self.sig.copy(), FS, setting)
                F.EMG_QRS_GATED = False
                try:
                    old = apply_emg_filter(self.sig.copy(), FS, setting)
                finally:
                    F.EMG_QRS_GATED = True
                d_fixed = abs(_j_mm(fixed, self.pk) - self.j_raw)
                d_old = abs(_j_mm(old, self.pk) - self.j_raw)
                self.assertLess(d_fixed, d_old,
                                f"EMG {setting} Hz: fallback {d_fixed:.3f} mm is no better "
                                f"than the plain low-pass {d_old:.3f} mm it replaced")


class TestCleanLeadIsUntouched(unittest.TestCase):
    """A clean lead still gets its QRS handed back exactly as recorded."""

    def setUp(self):
        _, self.sig = _beat_train(noise_uv=3.0, seed=3)
        self.pk = _r_peaks(self.sig)
        self.assertLessEqual(lead_noise_ratio(self.sig, FS), F.EMG_GATE_NOISE_LIMIT)

    def test_j_point_and_amplitude_unchanged(self):
        j0, pp0 = _j_mm(self.sig, self.pk), _qrs_pp_mm(self.sig, self.pk)
        for setting in ("25", "35", "40", "150"):
            with self.subTest(setting=setting):
                y = apply_emg_filter(self.sig.copy(), FS, setting)
                self.assertLess(abs(_j_mm(y, self.pk) - j0), 0.10)
                self.assertGreater(_qrs_pp_mm(y, self.pk) / pp0, 0.98)


class TestFallbackIsNeverNarrowerThanTheSetting(unittest.TestCase):
    """At EMG 150 the "protection" must not quietly become a 100 Hz low-pass."""

    def test_wide_setting_is_not_narrowed(self):
        _, sig = _beat_train(noise_uv=40.0, seed=11)
        pk = _r_peaks(sig)
        pp150 = _qrs_pp_mm(apply_emg_filter(sig.copy(), FS, "150"), pk)
        pp25 = _qrs_pp_mm(apply_emg_filter(sig.copy(), FS, "25"), pk)
        self.assertGreaterEqual(pp150, pp25 - 1e-9,
                                "150 Hz must not retain less QRS than 25 Hz")

    def test_constant_is_wide_enough_to_clear_the_qrs(self):
        self.assertGreaterEqual(F.EMG_GATE_FALLBACK_HZ, 100.0,
                                "a narrower fallback re-opens the J-point smearing")


class TestGateAndReportUseOneMeasurement(unittest.TestCase):
    """The report names leads using the same ratio the gate switches on.

    If these ever diverge the report would caution about one set of leads while a
    different set actually took the fallback path.
    """

    def test_ratio_matches_the_gate_decision(self):
        for uv, seed in ((3.0, 1), (10.0, 2), (25.0, 3), (60.0, 4)):
            with self.subTest(noise_uv=uv):
                _, sig = _beat_train(noise_uv=uv, seed=seed)
                ratio = lead_noise_ratio(sig, FS)
                from scipy.signal import butter, filtfilt
                b, a = butter(2, 60.0 / (FS / 2.0), btype="high")
                hf = float(np.std(filtfilt(b, a, sig)))
                span = float(np.percentile(sig, 99) - np.percentile(sig, 1))
                self.assertAlmostEqual(ratio, hf / span, places=9)

    def test_short_or_flat_input_is_not_called_noisy(self):
        self.assertEqual(lead_noise_ratio(np.zeros(50), FS), 0.0)
        self.assertEqual(lead_noise_ratio(np.zeros(5000), FS), 0.0)


class TestGateMaskCoversTheQRSAndNothingElse(unittest.TestCase):
    """The mask decides what gets handed back less filtered than the rest.

    It used to threshold at the 75th percentile of |signal| with a 300 ms minimum
    peak gap. At 59 bpm the T wave clears both, so it registered as a second R
    peak -- 20 peaks for 10 real beats in 8 of 12 leads on
    ECG_Report_..._A300_20260829_161810 -- and the muscle filter then handed the T
    wave back unfiltered, mains ripple included. That is what made the printed
    trace look fuzzy beside a commercial cart's.
    """

    def setUp(self):
        from scipy.signal import butter, filtfilt
        self.t, self.sig = _beat_train(secs=10.0, hr=59.0, noise_uv=6.0, seed=5)
        b, a = butter(2, [5 / (FS / 2), 35 / (FS / 2)], btype="band")
        self.view = filtfilt(b, a, self.sig - np.mean(self.sig))
        self.beats = len(_r_peaks(self.sig))

    def test_one_region_per_beat_not_two(self):
        from ecg.ecg_filters import detect_qrs_regions
        mask = detect_qrs_regions(self.view, FS)
        edges = int(np.sum(np.diff(mask.astype(int)) == 1))
        self.assertLessEqual(edges, self.beats + 1,
                             f"{edges} gated regions for {self.beats} beats - the T "
                             f"wave is being taken for a QRS")

    def test_duty_cycle_matches_a_qrs_not_a_qrs_plus_t_wave(self):
        """At ~59 bpm, +/-60 ms per beat is ~12% of the record. 32% means T waves."""
        from ecg.ecg_filters import detect_qrs_regions
        duty = detect_qrs_regions(self.view, FS).sum() / self.view.size
        self.assertLess(duty, 0.20,
                        f"gate covers {duty*100:.1f}% of the trace; a QRS-only mask "
                        f"at this rate is ~12%")
        self.assertGreater(duty, 0.05, "mask must still actually cover the QRS")

    def test_t_wave_is_not_inside_the_mask(self):
        from ecg.ecg_filters import detect_qrs_regions
        mask = detect_qrs_regions(self.view, FS)
        # The T wave in _beat_train() peaks 300 ms after R.
        for p in _r_peaks(self.sig):
            k = p + int(0.30 * FS)
            if k < mask.size:
                self.assertFalse(bool(mask[k]),
                                 "T wave peak fell inside the QRS gate")


class TestDiagnosticDefault(unittest.TestCase):
    """The shipped default is the diagnostic bandwidth, not a monitoring one."""

    def test_default_emg_cutoff_is_diagnostic(self):
        from utils.settings_manager import SettingsManager
        self.assertEqual(SettingsManager().default_settings["filter_emg"], "150",
                         "IEC 60601-2-25 asks for 150 Hz; 25/35/40 are operator choices")


if __name__ == "__main__":
    unittest.main(verbosity=2)
