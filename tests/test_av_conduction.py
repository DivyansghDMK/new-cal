"""AV conduction and age/sex ST threshold regression suite.

WHAT THIS PINS
--------------
Two things, both added because the device has a history of confident wrong
labels and neither may repeat it.

1. AV BLOCK DETECTION MUST NOT INVENT BLOCKS.

   The report already carried "Second-degree AV Block (Mobitz I)" on a tracing
   whose own printed measurements excluded it — a fixed 147 ms PR and a regular
   910 ms RR with no dropped beat. REPORT_ALLOWED_CONCLUSIONS exists to stop
   exactly that.

   The first version of av_conduction.py reproduced the same class of error from
   a different cause: when no P wave exists in the search window, taking the
   window extremum returns whatever sits at its boundary, so the measured PR came
   out at exactly P_SEARCH_MAX_MS. That produced four "First-degree AV Block"
   findings across the 116 real reports, three of them reading PR = 360 ms on
   recordings whose printed PR was 142-171 ms.

   The fix requires a genuine local peak, clear of both window edges. After it:
   4 of 4 synthetic blocks still detected, 0 of 116 real recordings called
   abnormal. Both halves are pinned below — a detector that finds nothing is as
   useless as one that finds everything.

2. ST ELEVATION THRESHOLDS ARE AGE- AND SEX-SPECIFIC IN V2-V3.

   Per Dr. Rahman's reference deck and the Fourth Universal Definition of MI:
   2.0 mm for men >= 40, 2.5 mm for men < 40, 1.5 mm for women, 1.0 mm elsewhere.
   The code applied a flat 1.0 mm everywhere with the note "age and sex are not
   captured" — which was untrue; patient_details carries both.

Run:
    python -m unittest tests.test_av_conduction -v
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from ecg.metrics.av_conduction import (  # noqa: E402
    analyse_av_conduction, P_SEARCH_MAX_MS, NOISE_LIMIT,
)
from ecg.interpretation import (  # noqa: E402
    st_elevation_threshold, st_findings, build_interpretation,
)

FS = 500.0
ADC_PER_MV = 1184.0


def _strip(pr_list, drop_after=None, rr_ms=850.0, p_amp=0.15):
    """Build a lead-II strip whose beats have the given PR intervals.

    drop_after: index of a beat whose P wave is present but not conducted.
    """
    n = int((len(pr_list) + 2) * rr_ms / 1000.0 * FS)
    t = np.arange(n) / FS
    x = np.zeros(n)
    r_peaks = []
    pos = 0.6
    for i, pr in enumerate(pr_list):
        p_at = pos
        qrs_at = pos + pr / 1000.0
        x += p_amp * np.exp(-((t - p_at) ** 2) / (2 * 0.022 ** 2))
        if drop_after is not None and i == drop_after:
            pos += rr_ms / 1000.0
            continue
        x += -0.12 * np.exp(-((t - (qrs_at - 0.012)) ** 2) / (2 * 0.006 ** 2))
        x += 1.40 * np.exp(-((t - qrs_at) ** 2) / (2 * 0.008 ** 2))
        x += -0.35 * np.exp(-((t - (qrs_at + 0.020)) ** 2) / (2 * 0.007 ** 2))
        x += 0.30 * np.exp(-((t - (qrs_at + 0.30)) ** 2) / (2 * 0.055 ** 2))
        r_peaks.append(int(qrs_at * FS))
        pos += rr_ms / 1000.0
    return x * ADC_PER_MV, np.array(r_peaks)


class TestRealBlocksAreDetected(unittest.TestCase):
    """A detector that finds nothing is as useless as one that finds everything."""

    def test_normal_conduction(self):
        sig, r = _strip([160] * 8)
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertEqual(out["classification"], "Normal AV conduction")

    def test_first_degree(self):
        sig, r = _strip([260] * 8)
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertEqual(out["classification"], "First-degree AV Block")

    def test_mobitz_i_wenckebach(self):
        sig, r = _strip([160, 200, 240, 160, 200, 240, 160, 200], drop_after=2)
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertEqual(out["classification"], "Second-degree AV Block (Mobitz I)")

    def test_mobitz_ii(self):
        sig, r = _strip([180] * 8, drop_after=4)
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertEqual(out["classification"], "Second-degree AV Block (Mobitz II)")


class TestNoBlockIsInvented(unittest.TestCase):
    """The failure mode this module was nearly shipped with."""

    def test_pr_never_lands_on_the_search_window_edge(self):
        """A PR of exactly P_SEARCH_MAX_MS means no P was found, not a long PR.

        This is the tell that the window extremum was taken instead of a real
        peak. It produced three "First-degree AV Block" findings reading 360 ms.
        """
        for pr in (140, 160, 200, 260):
            with self.subTest(pr=pr):
                sig, r = _strip([pr] * 8)
                out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
                for measured in out["pr_ms"]:
                    if measured is None:
                        continue
                    self.assertNotAlmostEqual(
                        measured, P_SEARCH_MAX_MS, delta=2.0,
                        msg=f"PR pinned to the search-window edge ({measured:.0f} ms)",
                    )

    def test_flat_trace_with_no_p_waves_claims_nothing(self):
        """No P wave anywhere must give "not assessable", never a block."""
        n = int(10 * FS)
        t = np.arange(n) / FS
        x = np.zeros(n)
        r_peaks = []
        for k in range(10):
            c = 0.5 + k * 0.85
            x += 1.4 * np.exp(-((t - c) ** 2) / (2 * 0.008 ** 2))     # QRS only
            x += 0.30 * np.exp(-((t - (c + 0.30)) ** 2) / (2 * 0.055 ** 2))
            r_peaks.append(int(c * FS))
        out = analyse_av_conduction(x * ADC_PER_MV, np.array(r_peaks), FS,
                                    noise_ratio=0.005)
        self.assertIsNone(out["classification"])
        self.assertFalse(out["assessable"])

    def test_noisy_lead_is_refused_outright(self):
        sig, r = _strip([160] * 8)
        out = analyse_av_conduction(sig, r, FS, noise_ratio=NOISE_LIMIT + 0.01)
        self.assertFalse(out["assessable"])
        self.assertIsNone(out["classification"])
        self.assertIn("noise", out["reason"])

    def test_too_few_beats_is_refused(self):
        sig, r = _strip([160] * 3)
        out = analyse_av_conduction(sig, r[:2], FS, noise_ratio=0.005)
        self.assertFalse(out["assessable"])

    def test_every_result_carries_a_reason(self):
        """Nothing may be returned without a stated justification."""
        for pr, drop, noise in ((160, None, 0.005), (260, None, 0.005),
                                (180, 4, 0.005), (160, None, 0.5)):
            sig, r = _strip([pr] * 8, drop_after=drop)
            out = analyse_av_conduction(sig, r, FS, noise_ratio=noise)
            self.assertTrue(out["reason"].strip(),
                            "a classification without a reason is not auditable")


class TestThirdDegreeIsNotProduced(unittest.TestCase):
    """The rule that labelled a third of all normal ECGs as complete heart block.

    A PR range wider than 80 ms with no dropped beat used to be reported as
    "Third-degree AV Block". Against cardiologist-annotated data that fired on
    55 of 167 normal LUDB records (33%) and 77 of 150 normal PTB-XL records
    (51%), plus 8 of 18 atrial fibrillation records, which have no P waves at
    all. The statistic was the defect, not the threshold: max-minus-min over ~10
    beats fires on one mis-detected P, and no robust replacement separated the
    false positives from the true ones.

    The rule is gone. These tests keep it gone.
    """

    def _wandering(self):
        """A strip whose PR varies far too much to be called fixed."""
        return _strip([140, 190, 150, 260, 160, 240, 145, 250])

    def test_third_degree_is_never_returned(self):
        sig, r = self._wandering()
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertNotEqual(out["classification"], "Third-degree AV Block")

    def test_one_outlier_beat_does_not_create_a_block(self):
        """LUDB record 27's shape: eight beats inside 16 ms and one outlier.

        Read as [168,168,170,174,176,180,184,184,356] it was reported as
        complete heart block. MAD was 8 ms.
        """
        sig, r = _strip([168, 168, 170, 174, 176, 180, 184, 184, 350])
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertNotEqual(out["classification"], "Third-degree AV Block")

    def test_a_wandering_pr_is_not_called_normal_either(self):
        """The same error in the opposite, quieter direction.

        Removing the third-degree branch must not let a wandering PR fall
        through to "Normal AV conduction". Normal conduction claims every P
        conducted at a CONSISTENT interval; without a fixed PR there is no
        claim to make.
        """
        sig, r = self._wandering()
        out = analyse_av_conduction(sig, r, FS, noise_ratio=0.005)
        self.assertIsNone(out["classification"])
        self.assertTrue(out["reason"].strip())

    def test_the_label_is_absent_from_the_module(self):
        """Grep-level guard: the string must not come back with a new rule."""
        import inspect
        from ecg.metrics import av_conduction
        src = inspect.getsource(av_conduction)
        assigns = [ln for ln in src.splitlines()
                   if '"Third-degree AV Block"' in ln and "=" in ln
                   and "classification" in ln and not ln.strip().startswith("#")]
        self.assertEqual(assigns, [],
                         "a rule now assigns Third-degree AV Block again — it needs "
                         "the atrial rate, not PR variability; see "
                         "docs/pending/av-block-labels.md")


class TestSTThresholdsFollowTheDeck(unittest.TestCase):
    """2.0 mm men >= 40, 2.5 mm men < 40, 1.5 mm women, 1.0 mm elsewhere."""

    def test_v2_v3_thresholds(self):
        self.assertEqual(st_elevation_threshold("V2", 45, "Male"), 2.0)
        self.assertEqual(st_elevation_threshold("V3", 39, "Male"), 2.5)
        self.assertEqual(st_elevation_threshold("V2", 30, "Female"), 1.5)
        self.assertEqual(st_elevation_threshold("V3", 70, "Female"), 1.5)

    def test_other_leads_stay_at_one_millimetre(self):
        for lead in ("I", "II", "aVF", "V1", "V4", "V5", "V6"):
            with self.subTest(lead=lead):
                self.assertEqual(st_elevation_threshold(lead, 45, "Male"), 1.0)

    def test_unknown_age_or_sex_falls_back_conservatively(self):
        """Missing demographics must not raise the bar and hide an elevation."""
        self.assertEqual(st_elevation_threshold("V2", None, None), 1.0)
        self.assertEqual(st_elevation_threshold("V2", 22, None), 1.0)
        self.assertEqual(st_elevation_threshold("V2", None, "Male"), 1.0)

    def test_same_elevation_different_patients(self):
        st = {"V2": 2.0, "V3": 2.1, "V4": 0.4}
        young_man = [f for f, _, _ in st_findings(st, 22, "Male")]
        older_man = [f for f, _, _ in st_findings(st, 45, "Male")]
        woman = [f for f, _, _ in st_findings(st, 30, "Female")]
        self.assertEqual(young_man, [], "2.0 mm is below the 2.5 mm bar for a man under 40")
        self.assertTrue(any("elevation" in f for f in older_man))
        self.assertTrue(any("elevation" in f for f in woman))

    def test_age_and_sex_reach_st_findings_through_build_interpretation(self):
        """The wiring, not just the thresholds — this is what was missing."""
        meas = {"HR": 72, "QRS": 92, "QTc": 410,
                "st_mm": {"V2": 2.0, "V3": 2.1}, "age": 22, "sex": "Male"}
        found = [f for f, _, _ in build_interpretation(meas, ["Normal Sinus Rhythm"])["statements"]]
        self.assertFalse([f for f in found if "elevation" in f])
        meas["age"] = 45
        found = [f for f, _, _ in build_interpretation(meas, ["Normal Sinus Rhythm"])["statements"]]
        self.assertTrue([f for f in found if "elevation" in f])


class TestNothingReachesTheReportYet(unittest.TestCase):
    """AV block labels are built but deliberately not printable.

    They need evidence and Dr. Rahman's sign-off before entering the allow-list.
    This test fails if one is added without the sign-off note being removed too.
    """

    def test_av_block_labels_are_not_in_the_allow_list(self):
        from ecg.ecg_report_generator import REPORT_ALLOWED_CONCLUSIONS
        for label in ("First-degree AV Block",
                      "Second-degree AV Block (Mobitz I)",
                      "Second-degree AV Block (Mobitz II)",
                      "Third-degree AV Block",
                      "Normal AV conduction"):
            self.assertNotIn(label, REPORT_ALLOWED_CONCLUSIONS,
                             f"{label!r} became printable — see docs/pending/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
