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

# A tracing is only NORMAL when every finding is one of these.
_NORMAL_FINDINGS = {"Normal Sinus Rhythm", "Narrow QRS"}

# Findings that are a deviation worth flagging but not, on their own, abnormal.
_BORDERLINE_FINDINGS = {"Sinus Bradycardia", "Sinus Tachycardia"}


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
        return f"QRSD {qrs}, < 120mS" if qrs else "QRSD < 120mS"
    if finding == "Wide QRS":
        return f"QRSD {qrs}, >= 120mS" if qrs else "QRSD >= 120mS"
    if finding == "Prolonged QTc":
        return f"QTc {qtc}, >= 460mS" if qtc else "QTc >= 460mS"
    if finding == "First-degree AV Block (Prolonged PR)":
        return f"PR {pr}, > 200mS" if pr else "PR > 200mS"
    return _STATIC_CRITERIA.get(finding, "")


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
                         lead_noise: Optional[Dict[str, float]] = None) -> Dict:
    """Assemble the findings box content.

    Returns statements as (finding, criterion) pairs, the overall
    classification, and the caveat that must accompany any machine reading.
    """
    kept = [str(f).strip() for f in (findings or []) if str(f).strip()]
    statements: List[Tuple[str, str]] = [(f, criterion_for(f, measurements)) for f in kept]

    artifact = artifact_statement(lead_noise)
    if artifact:
        statements.append((artifact, "high-frequency content"))

    # The artifact note describes the recording, not the heart, so it must not
    # push a clean tracing out of NORMAL.
    return {
        "statements": statements,
        "severity": classify(kept),
        "caveat": "Unconfirmed Diagnosis",
        "axis": {
            "P": measurements.get("p_axis", "--"),
            "QRS": measurements.get("QRS_axis", "--"),
            "T": measurements.get("t_axis", "--"),
        },
    }
