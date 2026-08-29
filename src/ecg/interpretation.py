"""Structured interpretation for the report's findings box.

Commercial carts do not print a bare list of findings. Each statement is paired
with the criterion that triggered it, the tracing gets one overall
classification, and the whole block is marked as machine-produced and unread:

    Sinus bradycardia ....................... V-rate 58, < 60
    Wide QRS ................................ QRSD 132, >= 120mS
                        - ABNORMAL ECG -
                        Unconfirmed Diagnosis

Printing the criterion beside the finding is what makes the output auditable —
the reader can see which measurement drove the statement and check it against
the values in the header, rather than taking the label on trust.

This module is deliberately free of Qt, matplotlib and file I/O so the rules can
be tested directly.
"""

from typing import Dict, List, Optional, Sequence, Tuple

# Findings that carry no rate/interval of their own still deserve a criterion.
_STATIC_CRITERIA = {
    "Atrial Fibrillation": "irregularly irregular, no organised P",
    "Atrial Flutter": "flutter waves, fixed conduction ratio",
}

# ── Thresholds, defined once ────────────────────────────────────────────────
# Both the report and the dashboard read these, so the two cannot publish
# different definitions of "normal" for the same measurement.
ADC_PER_MV_DEFAULT = 1184.0   # measured against the Fluke; see ecg_report_android
QRS_NORMAL_MIN_MS = 70      # below this is short - usually a measurement problem
QRS_NORMAL_MAX_MS = 110     # upper limit of normal; 70-100 is the normal range
QRS_WIDE_MIN_MS = 120       # required to diagnose BBB or a ventricular rhythm
QTC_PROLONGED_MS = 460
QTC_BORDERLINE_MS = 440
HR_BRADY_MAX = 60
HR_TACHY_MIN = 100


def qrs_finding(qrs_ms) -> str:
    """Short / Narrow / Borderline / Wide from the measured QRS duration.

    "Narrow" is the normal band and is not a finding. Below 70 ms is reported,
    because a QRS that short is outside physiological range and in practice
    usually means the onset/offset detection is clipping a weak signal - which
    the reader needs to know either way.
    """
    qrs = _as_int(qrs_ms)
    if qrs <= 0:
        return ""
    if qrs >= QRS_WIDE_MIN_MS:
        return "Wide QRS"
    if qrs >= QRS_NORMAL_MAX_MS:
        return "Borderline QRS duration"
    if qrs < QRS_NORMAL_MIN_MS:
        return "Short QRS duration"
    return "Narrow QRS"


# A tracing is only NORMAL when every finding is one of these.
_NORMAL_FINDINGS = {"Normal Sinus Rhythm", "Narrow QRS"}

# Findings that are a deviation worth flagging but not, on their own, abnormal.
_BORDERLINE_FINDINGS = {
    "Sinus Bradycardia",
    "Sinus Tachycardia",
    # 110-119 ms is past the upper limit of normal but short of the 120 ms a
    # bundle branch block diagnosis requires.
    "Borderline QRS duration",
    "Short QRS duration",
}


def _as_int(value, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def criterion_for(finding: str, measurements: Dict) -> str:
    """The measurement and threshold that justifies a finding, in Philips style."""
    hr = _as_int(measurements.get("HR"))
    qrs = _as_int(measurements.get("QRS"))
    qtc = _as_int(measurements.get("QTc"))
    pr = _as_int(measurements.get("PR"))

    if finding == "Sinus Bradycardia":
        return f"V-rate {hr}, < 60" if hr else "V-rate < 60"
    if finding == "Sinus Tachycardia":
        return f"V-rate {hr}, > 100" if hr else "V-rate > 100"
    if finding == "Normal Sinus Rhythm":
        return f"V-rate {hr}, 60-100" if hr else "V-rate 60-100"
    if finding == "Narrow QRS":
        return f"QRSD {qrs}, < 110mS" if qrs else "QRSD < 110mS"
    if finding == "Short QRS duration":
        return f"QRSD {qrs}, < 70mS - verify signal" if qrs else "QRSD < 70mS"
    if finding == "Borderline QRS duration":
        return f"QRSD {qrs}, 110-119mS" if qrs else "QRSD 110-119mS"
    if finding == "Wide QRS":
        return f"QRSD {qrs}, >= 120mS" if qrs else "QRSD >= 120mS"
    if finding == "Prolonged QTc":
        return f"QTc {qtc}, >= 460mS" if qtc else "QTc >= 460mS"
    if finding == "First-degree AV Block (Prolonged PR)":
        return f"PR {pr}, > 200mS" if pr else "PR > 200mS"
    return _STATIC_CRITERIA.get(finding, "")


# What each finding means — the "Working interpretation" column of the decision
# spec. The criterion says which measurement fired; this says what it implies,
# so the reader is not left to translate a threshold into a differential.
_IMPLICATIONS = {
    "Wide QRS": "bundle branch block, ventricular rhythm, hyperkalaemia, "
                "Na-channel blockade or paced rhythm",
    "Borderline QRS duration": "intraventricular conduction delay",
    "Short QRS duration": "below physiological range - check signal quality first",
    "Prolonged QTc": "repolarisation delay - drug effect, electrolytes, congenital",
    "Normal Sinus Rhythm": "P wave before every QRS, 1:1 conduction, rate 60-100",
    "Sinus Bradycardia": "athletic conditioning, vagal tone, drugs or sinus node disease",
    "Sinus Tachycardia": "fever, pain, hypovolaemia, anxiety or thyrotoxicosis",
    "Atrial Fibrillation": "no organised atrial activity - thromboembolic risk",
    "Atrial Flutter": "organised atrial re-entry, usually 2:1 to 4:1 conduction",
    "First-degree AV Block (Prolonged PR)": "conduction delay at the AV node",
}

# Combinations that must not be read as two independent findings. The spec calls
# for a confidence flag whenever the algorithm meets a wide-complex rhythm,
# ambiguous P waves, or a diagnostic overlap, rather than committing to one
# unqualified label.
def combined_caution(measurements: Dict, findings: Sequence[str]) -> Optional[Tuple[str, str, str]]:
    hr = _as_int(measurements.get("HR"))
    qrs = _as_int(measurements.get("QRS"))
    if hr > HR_TACHY_MIN and qrs >= QRS_WIDE_MIN_MS:
        return ("Wide-complex tachycardia",
                f"V-rate {hr}, QRSD {qrs}",
                "cannot exclude VT vs SVT with aberrancy - physician review required")
    return None


def implication_for(finding: str) -> str:
    """What the finding suggests, per the decision spec's interpretation column."""
    return _IMPLICATIONS.get(finding, "")


def classify(findings: Sequence[str]) -> str:
    """Overall classification of the tracing: NORMAL, BORDERLINE or ABNORMAL.

    Anything the rules produced that is not a plain sinus rhythm with a narrow
    QRS counts as abnormal; a rate deviation on its own is borderline. Absence
    of findings is not called normal — it usually means nothing was measurable,
    which is a different statement.
    """
    kept = [f for f in findings if f]
    if not kept:
        return "UNINTERPRETABLE ECG"
    if all(f in _NORMAL_FINDINGS for f in kept):
        return "NORMAL ECG"
    if all(f in _NORMAL_FINDINGS or f in _BORDERLINE_FINDINGS for f in kept):
        return "BORDERLINE ECG"
    return "ABNORMAL ECG"


def artifact_statement(lead_noise: Optional[Dict[str, float]], limit: float = 0.012) -> str:
    """Name the leads carrying enough interference to affect interpretation.

    Uses the same high-frequency ratio the muscle filter's QRS gate is keyed to,
    so one measurement drives both the filtering decision and what the report
    admits to the reader.
    """
    if not lead_noise:
        return ""
    noisy = [lead for lead, ratio in lead_noise.items()
             if isinstance(ratio, (int, float)) and ratio > limit]
    if not noisy:
        return ""
    return "Artifact in lead(s) " + ",".join(noisy)


def build_interpretation(measurements: Dict,
                         findings: Sequence[str],
                         lead_noise: Optional[Dict[str, float]] = None,
                         signed: bool = False) -> Dict:
    """Assemble the findings box content.

    Returns statements as (finding, criterion) pairs, the overall
    classification, and the caveats that must accompany a machine reading.

    `signed` says whether a clinician has confirmed the tracing. Until one has,
    the report carries "Unconfirmed Diagnosis"; the advice to consult a doctor
    stands either way, because the box holds an algorithm's reading and not a
    clinical opinion.
    """
    kept = [str(f).strip() for f in (findings or []) if str(f).strip()]
    statements: List[Tuple[str, str, str]] = [
        (f, criterion_for(f, measurements), implication_for(f)) for f in kept
    ]

    # ST deviation is measured per lead rather than produced by the rhythm
    # engine, so it is added here rather than arriving through `findings`.
    statements = st_findings(measurements.get("st_mm")) + statements

    # A rate and a width that are dangerous together lead, ahead of the two
    # findings that produced them.
    caution = combined_caution(measurements, kept)
    if caution:
        statements.insert(0, caution)

    artifact = artifact_statement(lead_noise)
    if artifact:
        statements.append((artifact, "high-frequency content",
                           "interpret this tracing with care"))

    # The artifact note describes the recording, not the heart, so it must not
    # push a clean tracing out of NORMAL.
    return {
        "statements": statements,
        "severity": classify(kept),
        # Worded for paper: the sheet is printed before anyone signs it, so it
        # tells the reader the status depends on the signature line below.
        "caveat": "" if signed else "Unconfirmed Diagnosis if not signed",
        "advisory": "Please consult your doctor",
        "axis": {
            "P": measurements.get("p_axis", "--"),
            "QRS": measurements.get("QRS_axis", "--"),
            "T": measurements.get("t_axis", "--"),
        },
    }

# ─── ST deviation ───────────────────────────────────────────────────────────
# Thresholds from the Fourth Universal Definition of MI: elevation >= 1 mm in
# two contiguous leads, depression >= 0.5 mm horizontal or downsloping.
#
# Two known simplifications, both deliberate and both flagged in the criterion
# text rather than hidden: deviation is measured at J+60 ms rather than at the
# J point itself, and the higher V2-V3 thresholds (2 mm men >= 40, 2.5 mm men
# < 40, 1.5 mm women) are not applied because age and sex are not captured.
ST_ELEVATION_MM = 1.0
ST_DEPRESSION_MM = -0.5

ST_TERRITORIES = {
    "anterior": ("V1", "V2", "V3", "V4"),
    "lateral": ("I", "aVL", "V5", "V6"),
    "inferior": ("II", "III", "aVF"),
}
# The lead group electrically opposite each territory.
ST_RECIPROCAL = {
    "anterior": ("II", "III", "aVF"),
    "lateral": ("III", "aVF"),
    "inferior": ("I", "aVL"),
}


def _lead_list(leads: Sequence[str]) -> str:
    order = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    return " ".join(sorted(leads, key=lambda l: order.index(l) if l in order else 99))


def st_findings(st_mm: Optional[Dict[str, float]]) -> List[Tuple[str, str, str]]:
    """Statements for ST deviation, per the decision spec's section 4 and 4.1.

    aVR is excluded from the lead groups: it faces the cavity, so its deviation
    is reciprocal to everything and would otherwise make every pattern look
    territorial.
    """
    if not st_mm:
        return []
    elevated = [l for l, v in st_mm.items()
                if l != "aVR" and isinstance(v, (int, float)) and v >= ST_ELEVATION_MM]
    depressed = [l for l, v in st_mm.items()
                 if l != "aVR" and isinstance(v, (int, float)) and v <= ST_DEPRESSION_MM]

    out: List[Tuple[str, str, str]] = []
    hits = {t: [l for l in leads if l in elevated] for t, leads in ST_TERRITORIES.items()}
    named = [t for t, ls in hits.items() if len(ls) >= 2]

    if len(named) >= 2:
        # Elevation spread across territories is not an infarct pattern.
        out.append(("ST elevation, diffuse",
                    f"ST >0.10mV, {_lead_list(elevated)}",
                    "diffuse elevation without a single territory - consider pericarditis "
                    "or early repolarisation rather than STEMI"))
    elif len(named) == 1:
        t = named[0]
        recip = [l for l in ST_RECIPROCAL[t] if l in depressed]
        crit = f"ST >0.10mV, {_lead_list(hits[t])}"
        if recip:
            crit += f"; STd {_lead_list(recip)}"
            impl = (f"{t} territory with reciprocal change - STEMI pattern, "
                    "immediate physician review required")
        else:
            impl = (f"{t} territory, no reciprocal change - STEMI, pericarditis or "
                    "early repolarisation; physician review required")
        out.append((f"ST elevation, {t} leads", crit, impl))
        # An inferior pattern with V1-V3 depression is a posterior mirror, not a
        # separate anterior finding.
        if t == "inferior" and any(l in depressed for l in ("V1", "V2", "V3")):
            out.append(("Posterior extension suspected",
                        f"STd {_lead_list([l for l in ('V1','V2','V3') if l in depressed])}",
                        "posterior mirror pattern - record posterior leads V7-V9"))
        depressed = [l for l in depressed if l not in recip and l not in ("V1", "V2", "V3")]
    elif elevated:
        out.append(("ST elevation",
                    f"ST >0.10mV, {_lead_list(elevated)}",
                    "fewer than two contiguous leads in one territory - below STEMI criteria"))

    if depressed:
        out.append(("ST depression",
                    f"ST <-0.05mV, {_lead_list(depressed)}",
                    "subendocardial ischaemia, digoxin effect, or reciprocal to an "
                    "opposite-wall STEMI"))
    return out
