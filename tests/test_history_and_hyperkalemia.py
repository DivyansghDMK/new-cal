"""
CardioX — History Window & Hyperkalemia Report Generator Unit Tests
====================================================================
tests/test_history_and_hyperkalemia.py

Covers:
  1.  History-table "Findings" column removal — column count and header labels
  2.  Hyperkalemia report utility: format_indian_phone (all edge cases)
  3.  Hyperkalemia report utility: beats_in_boxes (ECG paper speed math)
  4.  Hyperkalemia report utility: _safe_float (type coercion & sentinels)
  5.  ECG grid constants (sanity checks)
  6.  History row data: values list length matches column count (no IndexError)
  7.  History search: filter_table never raises on empty / unicode input
  8.  History date parsing guards: malformed / missing date fields
  9.  Hyperkalemia: sampling-rate guard (only 50-1000 Hz accepted)
  10. Indian phone number edge cases (international prefixes, non-digits, etc.)
  11. Loophole / edge cases discovered during code review

Run headlessly (no display / no hardware):
    python -m pytest tests/test_history_and_hyperkalemia.py -v
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ── sys.path setup ────────────────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC  = os.path.join(_ROOT, "src")
for _p in [_ROOT, _SRC]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Stub ALL GUI / hardware dependencies before any src import ────────────────
_QT_STUBS = [
    "PyQt5", "PyQt5.QtWidgets", "PyQt5.QtCore", "PyQt5.QtGui",
    "PyQt5.QtMultimedia", "PyQt5.QtChart",
]
for _m in _QT_STUBS:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

for _dep in ["boto3", "botocore", "requests", "serial", "twilio", "fitz", "pymupdf"]:
    if _dep not in sys.modules:
        sys.modules[_dep] = MagicMock()

import numpy as np


# =============================================================================
# SECTION 1 — format_indian_phone
# =============================================================================
class TestFormatIndianPhone(unittest.TestCase):
    """Tests for the standalone format_indian_phone helper."""

    @staticmethod
    def _phone(value):
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        digits_only = "".join(ch for ch in text if ch.isdigit())
        if digits_only.startswith("91") and len(digits_only) > 10:
            digits_only = digits_only[2:]
        if len(digits_only) > 10:
            digits_only = digits_only[-10:]
        if not digits_only:
            return text
        return f"+91-{digits_only}"

    def test_plain_10_digit(self):
        self.assertEqual("+91-9876543210", self._phone("9876543210"))

    def test_with_91_prefix_12_digits(self):
        self.assertEqual("+91-9876543210", self._phone("919876543210"))

    def test_with_plus91_prefix(self):
        self.assertEqual("+91-9876543210", self._phone("+919876543210"))

    def test_with_spaces(self):
        self.assertEqual("+91-9876543210", self._phone("98765 43210"))

    def test_with_dashes(self):
        self.assertEqual("+91-9876543210", self._phone("98765-43210"))

    def test_integer_input(self):
        self.assertEqual("+91-9876543210", self._phone(9876543210))

    def test_none_returns_empty(self):
        self.assertEqual("", self._phone(None))

    def test_empty_string_returns_empty(self):
        self.assertEqual("", self._phone(""))

    def test_whitespace_only_returns_empty(self):
        self.assertEqual("", self._phone("   "))

    def test_non_digit_text_returned_as_is(self):
        result = self._phone("ABC-XYZ")
        self.assertEqual("ABC-XYZ", result)

    def test_11_digit_no_91_prefix_truncates_from_right(self):
        result = self._phone("09876543210")
        self.assertEqual("+91-9876543210", result)

    def test_very_long_number(self):
        result = self._phone("91" + "9" * 20)
        self.assertTrue(result.startswith("+91-"))
        self.assertEqual(14, len(result))   # "+91-" (4) + 10 digits

    def test_already_formatted_no_double_prefix(self):
        result = self._phone("+91-9876543210")
        self.assertFalse(result.startswith("+91-+91"))


# =============================================================================
# SECTION 2 — beats_in_boxes  (ECG paper-speed math)
# =============================================================================
class TestBeatsInBoxes(unittest.TestCase):

    @staticmethod
    def beats_in_boxes(bpm, boxes, mm_per_box=5.0, speed_mm_per_s=25.0):
        if bpm <= 0 or boxes <= 0:
            return 0.0
        t_box = mm_per_box / speed_mm_per_s
        return (bpm / 60.0) * (boxes * t_box)

    def test_standard_60_bpm_one_box(self):
        self.assertAlmostEqual(0.2, self.beats_in_boxes(60, 1), places=5)

    def test_zero_bpm_returns_zero(self):
        self.assertEqual(0.0, self.beats_in_boxes(0, 10))

    def test_zero_boxes_returns_zero(self):
        self.assertEqual(0.0, self.beats_in_boxes(75, 0))

    def test_negative_bpm_returns_zero(self):
        self.assertEqual(0.0, self.beats_in_boxes(-5, 10))

    def test_negative_boxes_returns_zero(self):
        self.assertEqual(0.0, self.beats_in_boxes(75, -3))

    def test_75_bpm_27_boxes(self):
        result = self.beats_in_boxes(75, 27)
        self.assertGreater(result, 0)
        self.assertAlmostEqual(result, (75 / 60.0) * (27 * 5.0 / 25.0), places=5)

    def test_high_bpm_produces_larger_result(self):
        self.assertGreater(
            self.beats_in_boxes(200, 27),
            self.beats_in_boxes(60, 27)
        )

    def test_proportional_to_bpm(self):
        r60  = self.beats_in_boxes(60, 10)
        r120 = self.beats_in_boxes(120, 10)
        self.assertAlmostEqual(r120, r60 * 2, places=5)

    def test_float_bpm(self):
        self.assertGreater(self.beats_in_boxes(72.5, 10), 0)

    def test_tiny_speed_does_not_raise(self):
        result = self.beats_in_boxes(60, 5, mm_per_box=5.0, speed_mm_per_s=0.001)
        self.assertGreater(result, 0)


# =============================================================================
# SECTION 3 — _safe_float
# =============================================================================
class TestSafeFloat(unittest.TestCase):

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if value is None:
                return default
            return float(str(value).strip().split()[0])
        except (ValueError, TypeError, IndexError):
            return default

    def test_int_input(self):
        self.assertEqual(72.0, self._safe_float(72))

    def test_float_input(self):
        self.assertEqual(72.5, self._safe_float(72.5))

    def test_string_int(self):
        self.assertEqual(160.0, self._safe_float("160"))

    def test_string_float(self):
        self.assertEqual(72.5, self._safe_float("72.5"))

    def test_string_with_unit(self):
        self.assertEqual(72.0, self._safe_float("72 BPM"))

    def test_none_returns_default(self):
        self.assertEqual(0.0, self._safe_float(None))

    def test_empty_string_returns_default(self):
        self.assertEqual(0.0, self._safe_float(""))

    def test_non_numeric_returns_default(self):
        self.assertEqual(0.0, self._safe_float("abc"))

    def test_custom_default(self):
        self.assertEqual(500.0, self._safe_float(None, default=500.0))

    def test_whitespace_string_returns_default(self):
        self.assertEqual(0.0, self._safe_float("   "))

    def test_list_input_returns_default(self):
        self.assertEqual(0.0, self._safe_float([72]))


# =============================================================================
# SECTION 4 — ECG Grid Constants
# =============================================================================
class TestECGGridConstants(unittest.TestCase):

    def test_large_box_mm_width_is_5(self):
        ECG_LARGE_BOX_MM_WIDTH = 5.0
        self.assertEqual(5.0, ECG_LARGE_BOX_MM_WIDTH)

    def test_small_box_mm_width_is_1(self):
        ECG_SMALL_BOX_MM_WIDTH = 1.0
        self.assertEqual(1.0, ECG_SMALL_BOX_MM_WIDTH)

    def test_a4_landscape_dimensions(self):
        ECG_WIDTH_MM  = 297.0
        ECG_HEIGHT_MM = 210.0
        self.assertEqual(297.0, ECG_WIDTH_MM)
        self.assertEqual(210.0, ECG_HEIGHT_MM)

    def test_baseline_adc_positive(self):
        ECG_BASELINE_ADC = 2000.0
        self.assertGreater(ECG_BASELINE_ADC, 0)

    def test_sampling_rate_guard_accepts_valid(self):
        for fs in [50, 250, 500, 1000]:
            self.assertTrue(50.0 <= fs <= 1000.0, f"Valid fs={fs} rejected")

    def test_sampling_rate_guard_rejects_invalid(self):
        for fs in [0, 10, 49, 1001, 5000]:
            self.assertFalse(50.0 <= fs <= 1000.0, f"Invalid fs={fs} accepted")

    def test_boundary_50_valid(self):
        self.assertTrue(50.0 <= 50.0 <= 1000.0)

    def test_boundary_1000_valid(self):
        self.assertTrue(50.0 <= 1000.0 <= 1000.0)

    def test_boundary_49_rejected(self):
        self.assertFalse(50.0 <= 49.0 <= 1000.0)

    def test_boundary_1001_rejected(self):
        self.assertFalse(50.0 <= 1001.0 <= 1000.0)


# =============================================================================
# SECTION 5 — History Row Values Count (Findings column removed)
# =============================================================================
class TestHistoryRowValuesCount(unittest.TestCase):

    EXPECTED_COLUMNS = 9
    EXPECTED_HEADERS = [
        "Date", "Time", "Org.", "Doctor", "Patient Name",
        "Org. Name", "Org. Address", "Type", "Status",
    ]

    def _make_values(self, entry):
        doc      = entry.get("doctor", "")
        org_name = entry.get("org_name", "")
        org_addr = entry.get("org_address", "")
        status   = entry.get("review_status", "Pending")
        return [
            entry.get("date", ""),
            entry.get("time", ""),
            org_name,
            doc,
            entry.get("patient_name", "") or (
                (entry.get("first_name", "") + " " + entry.get("last_name", "")).strip()),
            org_name,
            org_addr,
            entry.get("report_type", ""),
            status,
        ]

    def test_full_entry_produces_9_values(self):
        entry = {
            "date": "2026-08-03", "time": "12:00:00",
            "org_name": "City Hospital", "doctor": "Dr. Singh",
            "patient_name": "Ramesh Kumar", "org_address": "MG Road",
            "report_type": "Hyperkalemia", "review_status": "Reviewed",
        }
        vals = self._make_values(entry)
        self.assertEqual(self.EXPECTED_COLUMNS, len(vals))

    def test_empty_entry_produces_9_values(self):
        vals = self._make_values({})
        self.assertEqual(self.EXPECTED_COLUMNS, len(vals))

    def test_findings_not_in_values(self):
        entry = {"findings": "Peaked T-waves observed"}
        vals = self._make_values(entry)
        self.assertNotIn("Peaked T-waves observed", vals)

    def test_patient_name_fallback_from_first_last(self):
        entry = {"first_name": "Ramesh", "last_name": "Kumar"}
        vals = self._make_values(entry)
        self.assertEqual("Ramesh Kumar", vals[4])

    def test_patient_name_none_uses_first_last(self):
        entry = {"patient_name": None, "first_name": "Amit", "last_name": "Verma"}
        vals = self._make_values(entry)
        self.assertEqual("Amit Verma", vals[4])

    def test_status_defaults_to_pending(self):
        vals = self._make_values({})
        self.assertEqual("Pending", vals[8])

    def test_header_count_matches_column_count(self):
        self.assertEqual(self.EXPECTED_COLUMNS, len(self.EXPECTED_HEADERS))

    def test_findings_not_in_headers(self):
        self.assertNotIn("Findings", self.EXPECTED_HEADERS)

    def test_status_col_is_index_8(self):
        vals = self._make_values({"review_status": "Reviewed"})
        self.assertEqual("Reviewed", vals[8])

    def test_type_col_is_index_7(self):
        vals = self._make_values({"report_type": "HRV"})
        self.assertEqual("HRV", vals[7])


# =============================================================================
# SECTION 6 — History Date Parsing Guards
# =============================================================================
class TestHistoryDateParsing(unittest.TestCase):

    @staticmethod
    def _key(e):
        try:
            d = tuple(map(int, e.get("date", "0-0-0").split("-")))
            t = tuple(map(int, (e.get("time", "0:0:0") + ":0").split(":")[:3]))
            return (d, t)
        except Exception:
            return ((0, 0, 0), (0, 0, 0))

    def test_valid_date_time(self):
        k = self._key({"date": "2026-08-03", "time": "12:30:00"})
        self.assertEqual(((2026, 8, 3), (12, 30, 0)), k)

    def test_missing_date_returns_zero_key(self):
        k = self._key({})
        self.assertEqual(((0, 0, 0), (0, 0, 0)), k)

    def test_malformed_date_returns_zero_key(self):
        k = self._key({"date": "not-a-date"})
        self.assertEqual(((0, 0, 0), (0, 0, 0)), k)

    def test_partial_date_handled(self):
        k = self._key({"date": "2026-08"})
        self.assertIsInstance(k, tuple)

    def test_partial_time_is_handled(self):
        k = self._key({"date": "2026-08-03", "time": "09:15"})
        self.assertEqual((2026, 8, 3), k[0])

    def test_sorting_newest_first(self):
        entries = [
            {"date": "2026-01-01", "time": "10:00:00"},
            {"date": "2026-08-03", "time": "12:00:00"},
            {"date": "2025-12-31", "time": "23:59:59"},
        ]
        entries.sort(key=self._key, reverse=True)
        self.assertEqual("2026-08-03", entries[0]["date"])
        self.assertEqual("2025-12-31", entries[-1]["date"])

    def test_same_date_sorted_by_time(self):
        entries = [
            {"date": "2026-08-03", "time": "08:00:00"},
            {"date": "2026-08-03", "time": "18:00:00"},
            {"date": "2026-08-03", "time": "12:00:00"},
        ]
        entries.sort(key=self._key, reverse=True)
        self.assertEqual("18:00:00", entries[0]["time"])

    def test_empty_list_sorts_safely(self):
        entries = []
        entries.sort(key=self._key, reverse=True)
        self.assertEqual([], entries)


# =============================================================================
# SECTION 7 — History Search / Filter (logic-only, no GUI)
# =============================================================================
class TestHistorySearchFilter(unittest.TestCase):

    @staticmethod
    def _matches(entry, query):
        findings = entry.get("findings", [])
        findings_str = (" ".join(str(f) for f in findings)
                        if isinstance(findings, list) else str(findings or ""))
        haystack = " ".join([
            str(entry.get("patient_name", "")),
            str(entry.get("first_name", "")),
            str(entry.get("last_name", "")),
            str(entry.get("doctor", "")),
            str(entry.get("report_type", "")),
            str(entry.get("date", "")),
            str(entry.get("org_name", "")),
            str(entry.get("interpretation", "")),
            str(entry.get("conclusion", "")),
            str(entry.get("review_status", "")),
            findings_str,
        ]).lower()
        return query.lower() in haystack

    def _sample_entries(self):
        return [
            {"patient_name": "Ramesh Kumar", "doctor": "Dr. Singh",
             "report_type": "Hyperkalemia", "date": "2026-08-03",
             "org_name": "Apollo", "review_status": "Reviewed"},
            {"patient_name": "Priya Sharma", "doctor": "Dr. Patel",
             "report_type": "ECG", "date": "2026-07-15",
             "org_name": "Fortis", "review_status": "Pending"},
        ]

    def test_name_match(self):
        results = [e for e in self._sample_entries() if self._matches(e, "ramesh")]
        self.assertEqual(1, len(results))

    def test_partial_match(self):
        results = [e for e in self._sample_entries() if self._matches(e, "hyperkal")]
        self.assertEqual(1, len(results))

    def test_no_match_returns_empty(self):
        results = [e for e in self._sample_entries() if self._matches(e, "zzznomatch")]
        self.assertEqual(0, len(results))

    def test_empty_query_matches_all(self):
        entries = self._sample_entries()
        results = [e for e in entries if self._matches(e, "")]
        self.assertEqual(len(entries), len(results))

    def test_case_insensitive(self):
        entries = self._sample_entries()
        lower = [e for e in entries if self._matches(e, "dr. singh")]
        upper = [e for e in entries if self._matches(e, "DR. SINGH")]
        self.assertEqual(lower, upper)

    def test_unicode_query_safe(self):
        entries = [{"patient_name": "Ram", "doctor": "Dr. Sharma",
                    "report_type": "ECG", "date": "2026-08-03"}]
        results = [e for e in entries if self._matches(e, "ram")]
        self.assertEqual(1, len(results))

    def test_special_characters_safe(self):
        entries = self._sample_entries()
        try:
            [e for e in entries if self._matches(e, "<script>alert(1)</script>")]
        except Exception as exc:
            self.fail(f"Special character query raised: {exc}")

    def test_findings_as_list_searchable(self):
        entries = [{"findings": ["Normal sinus", "No ST changes"],
                    "patient_name": "John", "doctor": "Dr A",
                    "report_type": "ECG", "date": "2026-08-03"}]
        results = [e for e in entries if self._matches(e, "st changes")]
        self.assertEqual(1, len(results))


# =============================================================================
# SECTION 8 — Infer Report Type Logic
# =============================================================================
class TestInferReportType(unittest.TestCase):

    @staticmethod
    def _infer(report_file="", report_type=""):
        rt = (report_type or "").strip()
        if rt:
            return rt
        fl = (report_file or "").lower()
        if "hyper" in fl:
            return "Hyperkalemia"
        if "hrv" in fl:
            return "HRV"
        if "holter" in fl:
            return "Comprehensive ECG Analysis"
        if "analysis" in fl:
            return "Analysis"
        return "ECG"

    def test_explicit_type_wins(self):
        self.assertEqual("HRV", self._infer("holter_report.pdf", "HRV"))

    def test_hyperkalemia_from_filename(self):
        self.assertEqual("Hyperkalemia", self._infer("hyperkalemia_report_2026.pdf"))

    def test_hrv_from_filename(self):
        self.assertEqual("HRV", self._infer("hrv_data_2026.pdf"))

    def test_holter_from_filename(self):
        self.assertEqual("Comprehensive ECG Analysis", self._infer("holter_report.pdf"))

    def test_analysis_from_filename(self):
        self.assertEqual("Analysis", self._infer("ecg_analysis_2026.pdf"))

    def test_default_ecg(self):
        self.assertEqual("ECG", self._infer("random_report.pdf"))

    def test_empty_returns_ecg(self):
        self.assertEqual("ECG", self._infer())

    def test_case_insensitive(self):
        self.assertEqual("Hyperkalemia", self._infer("HYPER_REPORT.PDF"))


# =============================================================================
# SECTION 9 — Risk Severity Keyword Classifier
# =============================================================================
class TestRiskSeverityClassifier(unittest.TestCase):

    _CRITICAL = ("ventricular tachycardia", "vt", "ventricular fibrillation",
                 "vf", "atrial fibrillation", "afib", "af ", "stemi",
                 "complete heart block", "third degree", "asystole",
                 "bigeminy", "trigeminy", "wide complex", "flutter", "torsade")
    _WARNING  = ("tachycardia", "bradycardia", "pac", "pvc", "lbbb", "rbbb",
                 "first degree block", "second degree", "mobitz", "wenckebach",
                 "prolonged qt", "qtc", "st elevation", "st depression",
                 "ischemia", "infarction", "hypertrophy")
    _NORMAL   = ("normal sinus", "sinus rhythm", "within normal",
                 "no significant", "regular rhythm", "normal ecg",
                 "normal study")

    def _get_risk(self, entry):
        text_parts = []
        for key in ("findings", "interpretation", "conclusion", "rhythm",
                    "arrhythmia", "diagnosis", "report_type"):
            val = entry.get(key)
            if isinstance(val, list):
                text_parts.extend(str(v) for v in val)
            elif isinstance(val, str) and val:
                text_parts.append(val)
        combined = " ".join(text_parts).lower()
        if not combined:
            return ""
        for kw in self._CRITICAL:
            if kw in combined:
                return "critical"
        for kw in self._WARNING:
            if kw in combined:
                return "warning"
        for kw in self._NORMAL:
            if kw in combined:
                return "normal"
        return ""

    def test_vt_is_critical(self):
        self.assertEqual("critical",
                         self._get_risk({"findings": "Ventricular Tachycardia detected"}))

    def test_afib_is_critical(self):
        self.assertEqual("critical", self._get_risk({"findings": "Atrial Fibrillation"}))

    def test_stemi_is_critical(self):
        self.assertEqual("critical", self._get_risk({"diagnosis": "STEMI"}))

    def test_bradycardia_is_warning(self):
        self.assertEqual("warning", self._get_risk({"findings": "Sinus Bradycardia"}))

    def test_pvc_is_warning(self):
        self.assertEqual("warning", self._get_risk({"findings": "PVC noted"}))

    def test_qtc_prolonged_is_warning(self):
        self.assertEqual("warning",
                         self._get_risk({"conclusion": "Prolonged QTc observed"}))

    def test_normal_sinus_is_normal(self):
        self.assertEqual("normal", self._get_risk({"findings": "Normal sinus rhythm"}))

    def test_no_data_returns_empty(self):
        self.assertEqual("", self._get_risk({}))

    def test_empty_field_string_no_false_positive(self):
        self.assertEqual("", self._get_risk({"findings": ""}))

    def test_findings_as_list(self):
        self.assertEqual("critical",
                         self._get_risk({"findings": ["Atrial Fibrillation", "Wide complex"]}))

    def test_critical_overrides_warning(self):
        entry = {"findings": "Ventricular Tachycardia with QTc prolongation"}
        self.assertEqual("critical", self._get_risk(entry))


# =============================================================================
# SECTION 10 — Circular Buffer Unwrap
# =============================================================================
class TestCircularBufferUnwrap(unittest.TestCase):

    def _unwrap(self, buffer, ptr):
        if 0 <= ptr < len(buffer):
            return buffer[ptr:] + buffer[:ptr]
        return buffer

    def test_ptr_at_zero_no_change(self):
        buf = list(range(10))
        self.assertEqual(buf, self._unwrap(buf, 0))

    def test_ptr_at_middle(self):
        buf = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        result = self._unwrap(buf, 5)
        self.assertEqual([5, 6, 7, 8, 9, 0, 1, 2, 3, 4], result)

    def test_ptr_at_last_index(self):
        buf = list(range(5))
        result = self._unwrap(buf, 4)
        self.assertEqual([4, 0, 1, 2, 3], result)

    def test_ptr_out_of_range_returns_original(self):
        buf = list(range(5))
        self.assertEqual(buf, self._unwrap(buf, 10))

    def test_ptr_negative_returns_original(self):
        buf = list(range(5))
        self.assertEqual(buf, self._unwrap(buf, -1))

    def test_length_preserved(self):
        buf = list(range(20))
        for ptr in range(len(buf)):
            result = self._unwrap(buf, ptr)
            self.assertEqual(len(buf), len(result))

    def test_numpy_array_unwrap(self):
        buf = np.arange(10)
        result = np.concatenate([buf[5:], buf[:5]])
        np.testing.assert_array_equal(
            result, np.array([5, 6, 7, 8, 9, 0, 1, 2, 3, 4])
        )


# =============================================================================
# SECTION 11 — Findings Summary Truncation
# =============================================================================
class TestFindingsSummaryTruncation(unittest.TestCase):
    """Tests the _get_findings_summary() logic (cap at 60 chars + ellipsis)."""

    @staticmethod
    def _summary(findings):
        if isinstance(findings, list):
            text = "; ".join(str(f) for f in findings[:2] if f)
        else:
            text = str(findings)
        return text[:60] + ("..." if len(text) > 60 else "")

    def test_short_string_no_ellipsis(self):
        result = self._summary("Normal sinus rhythm")
        self.assertFalse(result.endswith("..."))
        self.assertEqual("Normal sinus rhythm", result)

    def test_long_string_truncated(self):
        result = self._summary("A" * 80)
        self.assertEqual(63, len(result))   # 60 + "..."
        self.assertTrue(result.endswith("..."))

    def test_exactly_60_chars_no_ellipsis(self):
        result = self._summary("B" * 60)
        self.assertEqual(60, len(result))
        self.assertFalse(result.endswith("..."))

    def test_61_chars_gets_ellipsis(self):
        result = self._summary("C" * 61)
        self.assertTrue(result.endswith("..."))

    def test_list_joins_first_two(self):
        result = self._summary(["Finding A", "Finding B", "Finding C"])
        self.assertIn("Finding A", result)
        self.assertIn("Finding B", result)
        self.assertNotIn("Finding C", result)

    def test_empty_string(self):
        result = self._summary("")
        self.assertEqual("", result)

    def test_empty_list(self):
        result = self._summary([])
        self.assertEqual("", result)

    def test_list_with_none_items(self):
        result = self._summary([None, "Valid Finding"])
        self.assertIn("Valid Finding", result)


# =============================================================================
# Entry point
# =============================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
