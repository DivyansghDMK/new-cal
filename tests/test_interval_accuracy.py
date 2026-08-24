"""
Interval accuracy regression suite
==================================

Five consecutive 12-lead reports from one machine read QRS 83, 84, 84, 83,
83 ms while a reference device reported 138 ms on comparable signal. The QRS was
almost the same number every time because most of it was not a measurement.

THE CAUSE
---------
``_stabilize_to_reference()`` blended every interval toward a calibration table
indexed on heart rate::

    blended = measured * (1 - w) + table_value * w        w = 0.60
                                                          w = 0.75 for 150-200 bpm

The table's QRS is 85-87 ms at EVERY heart rate, so 60% of the reported QRS was
a near-constant ~86 ms and only 40% came from the patient. Verified against the
running code before the fix, predicted matched observed exactly:

    true QRS   measured (global 12-lead)   reported
      120 ms            134 ms              106 ms
      140 ms            152 ms              113 ms
      160 ms            172 ms              121 ms

The consequence was clinical, not cosmetic: a patient needed a TRUE QRS of
~170 ms before the report could print 120 ms, and a TRUE QTc of ~568 ms before
it could print 460 ms. "Wide QRS" and "Prolonged QTc" are two of the five
findings the report is permitted to state, and both were unreachable.

The file already made this argument for PR and exempted it. The exemption now
covers QRS, QT and QTc as well. RR stays anchored on purpose: it restates the
heart rate, so blending it carries no information and can hide nothing.

Run:
    python -m pytest tests/test_interval_accuracy.py -v
"""

import os
import sys
import unittest

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_ROOT, "src")
for _p in [_ROOT, _SRC]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from ecg.ecg_calculations import (                    # noqa: E402
    _stabilize_to_reference,
    calculate_all_ecg_metrics,
)
from ecg.metrics.reference_intervals import lookup_reference_intervals  # noqa: E402

FS = 500.0
WIDE_QRS_THRESHOLD = 120     # what the report calls "Wide QRS"
PROLONGED_QTC_THRESHOLD = 460


def synth_exact(qrs_ms, n=10000, hr=85, seed=0):
    """12-lead-able signal whose QRS is exactly zero outside its own window.

    Q, R and S lobes are half-sines with exact support, so the true width is
    unambiguous — Gaussian tails would make ground truth a matter of opinion.
    P and T are placed strictly outside the QRS window.
    """
    rng = np.random.default_rng(seed)
    sig = np.zeros(n)
    rr = 60.0 / hr
    nq = int(qrs_ms / 1000.0 * FS)
    t = np.arange(n) / FS
    k = 0
    while int((k * rr + 0.4) * FS) + nq < n:
        st = int((k * rr + 0.4) * FS)
        c = k * rr + 0.4
        x = np.linspace(0, 1, nq, endpoint=False)
        sig[st:st + nq] += (
            -140 * np.sin(np.pi * np.clip(x / 0.15, 0, 1)) * (x < 0.15)
            + 1000 * np.sin(np.pi * np.clip((x - 0.15) / 0.40, 0, 1)) * ((x >= 0.15) & (x < 0.55))
            - 320 * np.sin(np.pi * np.clip((x - 0.55) / 0.45, 0, 1)) * (x >= 0.55)
        )
        sig += 110 * np.exp(-0.5 * ((t - (c - 0.20)) / 0.024) ** 2)
        sig += 260 * np.exp(-0.5 * ((t - (c + qrs_ms / 1000.0 + 0.12)) / 0.05) ** 2)
        k += 1
    return sig + rng.normal(0, 4, n) + 2048.0


def measure_qrs(true_ms, tag):
    sig = synth_exact(true_ms, seed=true_ms)
    leads = {name: sig.copy() for name in
             ("I", "II", "III", "aVR", "aVL", "aVF",
              "V1", "V2", "V3", "V4", "V5", "V6")}
    m = calculate_all_ecg_metrics(sig, FS, instance_id=f"{tag}{true_ms}",
                                  all_lead_data=leads)
    return m["qrs_duration"]


# ══════════════════════════════════════════════════════════════════════════════
# 1. THE ANCHOR IS GONE FOR MEASURED INTERVALS
# ══════════════════════════════════════════════════════════════════════════════

class TestMeasuredIntervalsAreNotAnchored(unittest.TestCase):
    """A measured interval must be returned, not blended toward a normal."""

    _counter = 0

    def _stabilised(self, **metrics):
        """Stabilise with a FRESH state key.

        _stabilize_to_reference keeps per-instance state for its slew limiter,
        so reusing a key lets a previous call shift the result by a millisecond
        or two. That is the limiter working as intended; it just has to be
        isolated to test the anchoring in isolation.
        """
        metrics.setdefault("heart_rate", 85)
        TestMeasuredIntervalsAreNotAnchored._counter += 1
        return _stabilize_to_reference(
            dict(metrics), instance_id=f"iso_{self._counter}")

    def test_qrs_passes_through_unchanged(self):
        out = self._stabilised(qrs_duration=152)
        self.assertEqual(out["qrs_duration"], 152,
                         "QRS must not be pulled toward the calibration table")

    def test_qtc_passes_through_unchanged(self):
        out = self._stabilised(qtc_interval=500)
        self.assertEqual(out["qtc_interval"], 500)

    def test_qt_passes_through_unchanged(self):
        out = self._stabilised(qt_interval=430.0)
        self.assertAlmostEqual(out["qt_interval"], 430.0, places=3)

    def test_pr_still_passes_through(self):
        """PR was already exempt; it must stay that way."""
        out = self._stabilised(pr_interval=210)
        self.assertEqual(out["pr_interval"], 210)

    def test_wide_qrs_survives_at_every_heart_rate(self):
        for hr in (45, 60, 85, 110, 140, 170, 200):
            with self.subTest(hr=hr):
                out = _stabilize_to_reference(
                    {"heart_rate": hr, "qrs_duration": 140},
                    instance_id=f"hr_{hr}")
                self.assertEqual(out["qrs_duration"], 140,
                                 f"a 140 ms QRS was altered at {hr} bpm")

    def test_the_high_rate_band_no_longer_anchors_harder(self):
        """150-200 bpm used the heavier 0.75 weight — the worst case."""
        out = _stabilize_to_reference(
            {"heart_rate": 170, "qrs_duration": 150, "qtc_interval": 500},
            instance_id="highrate")
        self.assertEqual(out["qrs_duration"], 150)
        self.assertEqual(out["qtc_interval"], 500)

    def test_rr_is_still_anchored_on_purpose(self):
        """RR restates the heart rate, so blending hides nothing."""
        ref = lookup_reference_intervals(85.0)
        out = _stabilize_to_reference(
            {"heart_rate": 85, "rr_interval": 900.0}, instance_id="rr_anchor")
        self.assertNotEqual(out["rr_interval"], 900.0)
        self.assertLess(abs(out["rr_interval"] - ref["RR"]), 200.0)

    def test_missing_measurement_is_not_replaced_by_a_normal(self):
        """A zero means 'not measured', not 'normal'."""
        out = self._stabilised(qrs_duration=0)
        self.assertEqual(out["qrs_duration"], 0,
                         "an unmeasured QRS must not become a population normal")


# ══════════════════════════════════════════════════════════════════════════════
# 2. END-TO-END ACCURACY AGAINST KNOWN WIDTHS
# ══════════════════════════════════════════════════════════════════════════════

class TestQrsTracksTrueWidth(unittest.TestCase):

    def test_reported_qrs_increases_with_true_qrs(self):
        """Before the fix this was flat-to-falling: 98, 106, 113, 121."""
        widths = (100, 120, 140, 160)
        got = [measure_qrs(w, "mono") for w in widths]
        for a, b in zip(got, got[1:]):
            self.assertGreater(b, a, f"reported QRS did not increase: {got}")

    def test_wide_qrs_is_flagged_and_narrow_is_not(self):
        for true_ms, expect_wide in ((100, False), (140, True), (160, True)):
            with self.subTest(true_qrs=true_ms):
                got = measure_qrs(true_ms, "flag")
                self.assertEqual(got >= WIDE_QRS_THRESHOLD, expect_wide,
                                 f"true {true_ms} ms reported as {got} ms")

    def test_a_140ms_qrs_is_no_longer_reported_as_113(self):
        """The exact regression: 140 ms true used to report 113 ms."""
        got = measure_qrs(140, "reg")
        self.assertGreater(got, 125,
                           f"140 ms QRS still under-reported as {got} ms")

    def test_reported_value_is_within_a_stated_tolerance(self):
        """Residual bias is +12 to +14 ms from the 0.5-40 Hz analysis filter and
        the border delineation. That is documented, not silently accepted: this
        test fails if it drifts, so a future change cannot quietly widen it."""
        for true_ms in (100, 120, 140, 160):
            with self.subTest(true_qrs=true_ms):
                got = measure_qrs(true_ms, "tol")
                self.assertLessEqual(abs(got - true_ms), 20,
                                     f"true {true_ms} ms reported as {got} ms")


# ══════════════════════════════════════════════════════════════════════════════
# 3. THE FINDINGS THE REPORT IS ALLOWED TO STATE ARE REACHABLE
# ══════════════════════════════════════════════════════════════════════════════

class TestPermittedFindingsAreReachable(unittest.TestCase):
    """Restricting the report to five findings is pointless if two cannot fire."""

    def _required_true_value(self, reported_threshold, ref_value, weight):
        """What a patient needed BEFORE the fix for the report to flag it."""
        return (reported_threshold - weight * ref_value) / (1.0 - weight)

    def test_old_blend_made_wide_qrs_practically_unreachable(self):
        """Documents the magnitude the fix removed."""
        ref = lookup_reference_intervals(85.0)
        needed = self._required_true_value(WIDE_QRS_THRESHOLD, ref["QRS"], 0.60)
        self.assertGreater(needed, 160,
                           "if this drops, re-check whether the anchor returned")

    def test_old_blend_made_prolonged_qtc_practically_unreachable(self):
        ref = lookup_reference_intervals(85.0)
        needed = self._required_true_value(PROLONGED_QTC_THRESHOLD + 1,
                                           ref["QTc"], 0.60)
        self.assertGreater(needed, 550)

    def test_wide_qrs_is_now_reachable(self):
        out = _stabilize_to_reference(
            {"heart_rate": 85, "qrs_duration": 125}, instance_id="reach_qrs")
        self.assertGreaterEqual(out["qrs_duration"], WIDE_QRS_THRESHOLD)

    def test_prolonged_qtc_is_now_reachable(self):
        out = _stabilize_to_reference(
            {"heart_rate": 85, "qtc_interval": 470}, instance_id="reach_qtc")
        self.assertGreater(out["qtc_interval"], PROLONGED_QTC_THRESHOLD)


# ══════════════════════════════════════════════════════════════════════════════
# 4. THE ANTI-JITTER MACHINERY IS STILL THERE
# ══════════════════════════════════════════════════════════════════════════════

class TestStabilityMachineryIntact(unittest.TestCase):
    """The function exists to stop jitter; only the pull to normal was removed."""

    def test_slew_limiter_still_present(self):
        with open(os.path.join(_ROOT, "src/ecg/ecg_calculations.py"),
                  "r", encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("_limit_step", src)
        self.assertIn("_REFERENCE_SLEW_LIMITS", src)

    def test_median_deadband_smoothing_still_present(self):
        from ecg.ecg_calculations import apply_interval_smoothing
        buf = {}
        for _ in range(10):
            out = apply_interval_smoothing(100, "jitter", buf)
        self.assertEqual(out, 100)
        # A 2 ms wobble must not move the reported value.
        out = apply_interval_smoothing(102, "jitter", buf)
        self.assertEqual(out, 100, "deadband no longer suppresses small drift")


if __name__ == "__main__":
    unittest.main(verbosity=2)
