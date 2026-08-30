"""Beat-by-beat P wave detection, PR measurement, and AV conduction analysis.

WHY THIS EXISTS
---------------
`clinical_measurements.measure_pr_from_median_beat()` measures PR on the MEDIAN
beat — one averaged complex — and returns a single number. That is the right
answer for "what is this patient's PR interval", and it is what the report header
prints. It cannot answer the questions the AV blocks are defined by, all of which
are about how PR and conduction change FROM BEAT TO BEAT:

    1st degree     every P conducts, PR fixed and > 200 ms
    2nd Mobitz I   PR lengthens progressively, then one P is not conducted
    2nd Mobitz II  PR fixed, then one P is suddenly not conducted
    3rd degree     P and QRS are independent — no consistent PR at all

Averaging destroys exactly the information that separates these. A Wenckebach
cycle of PR 160/200/240/dropped averages to a single unremarkable ~200 ms.

WHAT THIS DOES NOT DO
---------------------
It produces measurements and a classification. It does NOT add anything to
REPORT_ALLOWED_CONCLUSIONS, and nothing here reaches a printed report yet. The
allow-list exists because rhythm classifiers on this device produced dangerous
false positives — a normal 65 bpm sinus ECG was once reported as "Ventricular
Fibrillation", and a normal tracing with a fixed 147 ms PR was reported as
"Second-degree AV Block (Mobitz I)". Any label from this module has to earn its
way past that history with evidence, and past Dr. Rahman with a signature.

A TEN-SECOND STRIP IS SHORT
---------------------------
At 60 bpm a 10 s strip holds ~10 beats. A Wenckebach cycle can be 3-4 beats, so
one strip may hold two cycles, or one, or a fragment. Mobitz II can be entirely
absent from a 10 s window in a patient who has it. This module reports what it
can see and says how much it saw; it does not extrapolate to a burden or a
diagnosis of absence.
"""

from typing import Dict, List, Optional

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

# ── Thresholds ───────────────────────────────────────────────────────────────
# From the ECG_Reference_Deck (Dr. Razzakur Rahman) and the standard definitions.
PR_NORMAL_MIN_MS = 120.0     # below this suggests pre-excitation (e.g. WPW)
PR_NORMAL_MAX_MS = 200.0     # above this, fixed, is first-degree block

# P is searched for in this window before the R peak. The upper bound has to
# clear a prolonged PR (a first-degree block can reach 300-400 ms) without
# reaching back into the previous T wave.
P_SEARCH_MIN_MS = 80.0
P_SEARCH_MAX_MS = 360.0

# A PR that varies by more than this across conducted beats is not "fixed".
# Beat-to-beat PR jitter on a clean trace measures a few milliseconds; 20 ms is
# comfortably above the measurement noise and well below the 40-80 ms steps a
# Wenckebach cycle produces.
PR_FIXED_TOLERANCE_MS = 20.0

# Wenckebach needs the increments to actually be increments, not jitter.
PR_INCREMENT_MIN_MS = 15.0

# Above this per-lead high-frequency ratio the P wave cannot be trusted, so no
# conduction claim is made. Same measurement the muscle filter's gate uses; see
# ecg_filters.lead_noise_ratio(). 0.012 is the gate's own limit and 0.06 is where
# a J point stops being measurable at all, so this sits deliberately between.
NOISE_LIMIT = 0.030


def _bandpass(sig: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    nyq = fs / 2.0
    lo_n = max(lo / nyq, 1e-4)
    hi_n = min(hi / nyq, 0.99)
    if lo_n >= hi_n:
        return np.asarray(sig, dtype=float)
    b, a = butter(2, [lo_n, hi_n], btype="band")
    return filtfilt(b, a, np.asarray(sig, dtype=float))


def _qrs_onset(sig: np.ndarray, r_idx: int, fs: float) -> Optional[int]:
    """Walk back from the R peak to where the complex leaves the baseline.

    PR is measured from P ONSET to QRS ONSET, not peak to peak. Using the R peak
    instead would inflate every PR by the width of the Q-R upstroke, and would
    make PR track QRS morphology changes that have nothing to do with conduction.
    """
    look = int(0.10 * fs)
    start = max(0, r_idx - look)
    seg = sig[start:r_idx + 1]
    if seg.size < 4:
        return None
    slope = np.abs(np.diff(seg))
    if slope.size == 0 or slope.max() <= 0:
        return None
    # The onset is where the slope first rises above a small fraction of the
    # steepest part of the upstroke, searching backwards from the peak.
    thresh = slope.max() * 0.10
    idx = np.where(slope > thresh)[0]
    if idx.size == 0:
        return None
    return start + int(idx[0])


def _p_wave(sig: np.ndarray, qrs_on: int, fs: float,
            prev_r: Optional[int]) -> Optional[Dict]:
    """Find the P wave preceding one QRS onset. Returns its peak and onset."""
    lo = qrs_on - int(P_SEARCH_MAX_MS / 1000.0 * fs)
    hi = qrs_on - int(P_SEARCH_MIN_MS / 1000.0 * fs)
    # Never search back past the previous QRS, or a previous T wave gets taken
    # for a P wave — the mistake that produced spurious block findings before.
    if prev_r is not None:
        lo = max(lo, prev_r + int(0.20 * fs))
    if lo < 0:
        lo = 0
    if hi <= lo + 2:
        return None

    win = sig[lo:hi]
    if win.size < 5:
        return None
    base = float(np.median(win))
    dev = win - base

    # The P wave must be a genuine LOCAL PEAK inside the window, not merely the
    # largest value in it.
    #
    # Taking the window extremum is how this goes wrong: when there is no P wave
    # to find, the extremum lands on whatever is at the window boundary - usually
    # the tail of the previous T wave - and the measured PR then comes out at
    # exactly P_SEARCH_MAX_MS. An early version of this module did that and
    # produced four "First-degree AV Block" findings, three of them reading PR =
    # 360 ms, on recordings whose printed PR was 142-171 ms. That is precisely
    # the class of false positive REPORT_ALLOWED_CONCLUSIONS exists to stop.
    #
    # So: require a real peak, and reject one that sits against either edge of
    # the search window, because an edge peak means the true extremum lies
    # outside it and we are looking at the flank of something else.
    noise = float(np.std(dev))
    if noise <= 0:
        return None
    min_amp = 3.0 * noise
    edge = max(2, int(0.012 * fs))          # 12 ms of clearance at each end

    best = None
    for signed in (dev, -dev):              # upright, then inverted P
        idx, _ = find_peaks(signed, height=min_amp)
        idx = [i for i in idx if edge <= i < win.size - edge]
        if not idx:
            continue
        cand = int(max(idx, key=lambda i: signed[i]))
        if best is None or abs(dev[cand]) > abs(dev[best]):
            best = cand
    if best is None:
        return None
    peak_i = best
    amp = float(dev[peak_i])

    # Onset: walk back from the P peak to where it leaves the baseline.
    j = peak_i
    thr = abs(amp) * 0.20
    while j > 0 and abs(dev[j]) > thr:
        j -= 1
    return {
        "peak": lo + peak_i,
        "onset": lo + j,
        "amplitude": amp,
        "upright": amp > 0,
    }


def analyse_av_conduction(lead_ii: np.ndarray, r_peaks, fs: float = 500.0,
                          noise_ratio: Optional[float] = None) -> Dict:
    """Beat-by-beat PR and an AV conduction classification for one strip.

    Returns a dict with:
        pr_ms            list, one per beat: PR in ms, or None if no P was found
        conducted        list of bool, whether a P was found for that QRS
        p_count          P waves detected, including any not followed by a QRS
        qrs_count        QRS complexes
        classification   one of: "Normal AV conduction", "First-degree AV Block",
                         "Second-degree AV Block (Mobitz I)",
                         "Second-degree AV Block (Mobitz II)",
                         "Third-degree AV Block", or None when not assessable
        reason           plain-text justification, always populated
        assessable       False when the trace is too noisy or too short
    """
    out = {
        "pr_ms": [], "conducted": [], "p_count": 0, "qrs_count": 0,
        "classification": None, "reason": "", "assessable": False,
        "pr_median_ms": None, "pr_range_ms": None,
    }
    sig = np.asarray(lead_ii, dtype=float)
    r_peaks = np.asarray(r_peaks, dtype=int)
    out["qrs_count"] = int(r_peaks.size)

    if noise_ratio is not None and noise_ratio > NOISE_LIMIT:
        out["reason"] = (f"lead II noise ratio {noise_ratio:.3f} exceeds "
                         f"{NOISE_LIMIT:.3f}; P waves are not reliable")
        return out
    if r_peaks.size < 4:
        out["reason"] = f"only {r_peaks.size} beats; need at least 4"
        return out

    filt = _bandpass(sig, fs, 0.5, 40.0)

    prs: List[Optional[float]] = []
    for n, r in enumerate(r_peaks):
        onset = _qrs_onset(filt, int(r), fs)
        if onset is None:
            prs.append(None)
            continue
        prev_r = int(r_peaks[n - 1]) if n > 0 else None
        p = _p_wave(filt, onset, fs, prev_r)
        if p is None:
            prs.append(None)
            continue
        prs.append((onset - p["onset"]) / fs * 1000.0)

    out["pr_ms"] = prs
    out["conducted"] = [p is not None for p in prs]
    valid = [p for p in prs if p is not None]
    out["p_count"] = len(valid)

    if len(valid) < 3:
        out["reason"] = (f"P wave found on only {len(valid)} of {r_peaks.size} "
                         f"beats; conduction not assessable")
        return out

    out["assessable"] = True
    med = float(np.median(valid))
    rng = float(max(valid) - min(valid))
    out["pr_median_ms"] = med
    out["pr_range_ms"] = rng

    # ── Dropped beats: an RR roughly double its neighbours, with a P inside ──
    rr = np.diff(r_peaks) / fs * 1000.0
    rr_med = float(np.median(rr)) if rr.size else 0.0
    dropped = [i for i, v in enumerate(rr) if rr_med > 0 and v >= 1.65 * rr_med]

    fixed = rng <= PR_FIXED_TOLERANCE_MS

    if dropped:
        # Does PR lengthen across the beats leading into the pause?
        wenckebach = False
        for d in dropped:
            run = [prs[i] for i in range(max(0, d - 2), d + 1) if prs[i] is not None]
            if len(run) >= 2:
                steps = np.diff(run)
                if np.all(steps > 0) and float(np.sum(steps)) >= PR_INCREMENT_MIN_MS:
                    wenckebach = True
                    break
        if wenckebach:
            out["classification"] = "Second-degree AV Block (Mobitz I)"
            out["reason"] = (f"PR lengthens progressively then a beat is dropped; "
                             f"PR {min(valid):.0f}-{max(valid):.0f} ms over "
                             f"{len(valid)} conducted beats")
        elif fixed:
            out["classification"] = "Second-degree AV Block (Mobitz II)"
            out["reason"] = (f"PR fixed at {med:.0f} ms (range {rng:.0f} ms) with a "
                             f"non-conducted P wave")
        else:
            out["classification"] = None
            out["reason"] = (f"a long pause is present but PR is neither fixed "
                             f"({rng:.0f} ms range) nor progressively lengthening; "
                             f"not classifiable from this strip")
        return out

    # ── No dropped beat ──────────────────────────────────────────────────────
    if not fixed and rng > 80.0:
        # PR wandering this much with no dropped beat suggests P and QRS are not
        # related at all. Genuine dissociation also needs the atrial rate to be
        # faster than the ventricular one, which a 10 s strip may not settle.
        out["classification"] = "Third-degree AV Block"
        out["reason"] = (f"no consistent PR relationship (range {rng:.0f} ms across "
                         f"{len(valid)} beats) — possible AV dissociation")
        return out

    if fixed and med > PR_NORMAL_MAX_MS:
        out["classification"] = "First-degree AV Block"
        out["reason"] = (f"PR fixed at {med:.0f} ms (range {rng:.0f} ms), > "
                         f"{PR_NORMAL_MAX_MS:.0f} ms, every P conducted")
        return out

    if fixed and med < PR_NORMAL_MIN_MS:
        out["classification"] = None
        out["reason"] = (f"PR {med:.0f} ms is below {PR_NORMAL_MIN_MS:.0f} ms — "
                         f"consider pre-excitation; not an AV block")
        return out

    out["classification"] = "Normal AV conduction"
    out["reason"] = (f"PR {med:.0f} ms (range {rng:.0f} ms), every P conducted, "
                     f"no dropped beats in {r_peaks.size} beats")
    return out
