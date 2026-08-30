#!/usr/bin/env python3
"""Validate this device's measurements against cardiologist-annotated reference data.

WHY
---
Our own recordings carry no truth label, so nothing measured on them can be
checked. A rule that is wrong on every strip looks exactly like a rule that is
right on every strip. Two public datasets fix that, and both are 12-lead at
500 Hz -- the same acquisition as this device:

  LUDB    200 records. Two cardiologists annotated P, QRS and T onset/peak/offset
          PER LEAD PER BEAT, plus a diagnosis per record. This gives ground truth
          for the interval measurements the report header prints.
          physionet.org/content/ludb/1.0.1/

  PTB-XL  21799 records with an SCP-coded cardiologist report each. No per-beat
          boundaries, but far more pathology -- including the Mobitz cases LUDB
          has none of. physionet.org/content/ptb-xl/1.0.3/

WHAT IT FOUND (see docs/REFERENCE_VALIDATION.md)
  - QRS duration reads ~18 ms SHORT against cardiologist boundaries, confirmed
    on two independent code paths over 195 records.
  - The AV conduction module labelled 33-51% of NORMAL records as complete
    heart block.
  - PR was pinning to its search-window edge on 29% of LUDB records.

SETUP
-----
    pip install wfdb          # keep numpy < 2; matplotlib 3.7 breaks on numpy 2
    python tools/validate_against_reference.py --fetch --data ~/ecg-reference

USAGE
-----
    python tools/validate_against_reference.py --data ~/ecg-reference intervals
    python tools/validate_against_reference.py --data ~/ecg-reference avblock
"""
import argparse, os, sys, csv, ast, json, glob, collections, warnings
warnings.filterwarnings("ignore")
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
ADC_PER_MV = 1184.0
LEADS = ["i", "ii", "iii", "avr", "avl", "avf", "v1", "v2", "v3", "v4", "v5", "v6"]
LUDB_URL = "https://physionet.org/files/ludb/1.0.1/data"


def fetch(data_dir):
    """Download LUDB signals and lead-II annotations (~30 MB)."""
    import urllib.request
    d = os.path.join(data_dir, "ludb")
    os.makedirs(d, exist_ok=True)
    urllib.request.urlretrieve("https://physionet.org/files/ludb/1.0.1/ludb.csv",
                               os.path.join(d, "ludb.csv"))
    for i in range(1, 201):
        for ext in ("hea", "dat", "ii"):
            p = os.path.join(d, f"{i}.{ext}")
            if os.path.exists(p):
                continue
            try:
                urllib.request.urlretrieve(f"{LUDB_URL}/{i}.{ext}", p)
            except Exception as e:
                print(f"  {i}.{ext}: {e}")
        if i % 25 == 0:
            print(f"  {i}/200")
    print(f"LUDB in {d}")


def reference_intervals(rec_id, d):
    """Median PR / QRS / QT in ms from the LUDB lead-II annotations.

    LUDB marks each wave as '(' onset, a peak symbol (p/N/t), then ')' offset.
        PR  = QRS onset - P onset
        QRS = QRS offset - QRS onset
        QT  = T offset - QRS onset
    """
    import wfdb
    a = wfdb.rdann(os.path.join(d, str(rec_id)), "ii")
    sym, pos = list(a.symbol), list(a.sample)
    waves = [(s, pos[k - 1], pos[k + 1])
             for k, s in enumerate(sym)
             if s in "pNt" and 0 < k < len(sym) - 1
             and sym[k - 1] == "(" and sym[k + 1] == ")"]
    pr, qrs, qt = [], [], []
    for k, (s, on, off) in enumerate(waves):
        if s != "N":
            continue
        qrs.append(off - on)
        if k and waves[k - 1][0] == "p":
            pr.append(on - waves[k - 1][1])
        if k + 1 < len(waves) and waves[k + 1][0] == "t":
            qt.append(waves[k + 1][2] - on)
    ms = lambda v: float(np.median(v)) * 1000.0 / 500.0 if v else None
    return ms(pr), ms(qrs), ms(qt)


def measured_intervals(rec_id, d):
    """PR / QRS / QT exactly as the report header gets them."""
    import wfdb
    from ecg.ecg_calculations import calculate_all_ecg_metrics
    rec = wfdb.rdrecord(os.path.join(d, str(rec_id)))
    nm = [n.lower() for n in rec.sig_name]
    all_leads = {L.upper(): rec.p_signal[:, nm.index(L)] * ADC_PER_MV
                 for L in LEADS if L in nm}
    m = calculate_all_ecg_metrics(rec.p_signal[:, nm.index("ii")] * ADC_PER_MV,
                                  rec.fs, instance_id=f"ref{rec_id}",
                                  all_lead_data=all_leads)
    out = []
    for k in ("pr_interval", "qrs_duration", "qt_interval"):
        v = m.get(k)
        out.append(float(v) if isinstance(v, (int, float)) and v > 0 else None)
    return tuple(out)


def cmd_intervals(d):
    rows = []
    for i in range(1, 201):
        if not os.path.exists(os.path.join(d, f"{i}.ii")):
            continue
        try:
            t = reference_intervals(i, d)
        except Exception:
            continue
        try:
            o = measured_intervals(i, d)
        except Exception:
            o = (None, None, None)
        rows.append((i, t, o))

    print(f"\nREPORT INTERVALS vs LUDB cardiologist annotations   n={len(rows)}\n")
    print(f"{'':>5} {'n':>4} {'ours':>6} {'ref':>6} {'bias':>6} "
          f"{'med|err|':>9} {'<=10ms':>7} {'<=20ms':>7} {'no value':>9}")
    for k, name in ((0, "PR"), (1, "QRS"), (2, "QT")):
        pairs = [(o[k], t[k]) for _, t, o in rows if t[k] and o[k]]
        missing = sum(1 for _, t, o in rows if t[k] and not o[k])
        if not pairs:
            print(f"{name:>5}  no paired measurements")
            continue
        ov = np.array([a for a, _ in pairs]); tv = np.array([b for _, b in pairs])
        d_ = ov - tv; ad = np.abs(d_)
        print(f"{name:>5} {len(pairs):>4} {np.median(ov):>6.0f} {np.median(tv):>6.0f} "
              f"{np.median(d_):>+6.0f} {np.median(ad):>9.0f} "
              f"{100*np.mean(ad<=10):>6.0f}% {100*np.mean(ad<=20):>6.0f}% {missing:>9}")
    print("\nA bias larger than a few ms is systematic, not scatter. QRS matters most:\n"
          "the 'Wide QRS' conclusion triggers at 120 ms, so a short read hides it.")


def cmd_avblock(d):
    import wfdb
    from ecg.metrics.av_conduction import analyse_av_conduction
    from ecg.arrhythmia_detector import detect_r_peaks_pan_tompkins
    try:
        from ecg.ecg_filters import lead_noise_ratio
    except Exception:
        lead_noise_ratio = None

    truth = {}
    for r in csv.DictReader(open(os.path.join(d, "ludb.csv"))):
        c = (r["Conduction abnormalities"] or "").lower()
        rh = (r["Rhythms"] or "").lower()
        truth[r["ID"]] = ("3AVB" if "iii degree" in c else
                          "2AVB" if ("ii degree" in c or "mobitz" in c) else
                          "1AVB" if "i degree av" in c else
                          "AF" if ("fibrill" in rh or "flutter" in rh) else "NORM")

    lab = {"Normal AV conduction": "NORM", "First-degree AV Block": "1AVB",
           "Second-degree AV Block (Mobitz I)": "2AVB",
           "Second-degree AV Block (Mobitz II)": "2AVB",
           "Third-degree AV Block": "3AVB"}
    grid, tot = collections.Counter(), collections.Counter()
    for i in range(1, 201):
        p = os.path.join(d, str(i))
        if not os.path.exists(p + ".hea"):
            continue
        t = truth.get(str(i), "?")
        tot[t] += 1
        try:
            rec = wfdb.rdrecord(p)
            nm = [n.lower() for n in rec.sig_name]
            sig = rec.p_signal[:, nm.index("ii") if "ii" in nm else 1]
            r = np.asarray(detect_r_peaks_pan_tompkins(sig, rec.fs), dtype=int)
            nr = float(lead_noise_ratio(sig, rec.fs)) if lead_noise_ratio else None
            o = analyse_av_conduction(sig, r, rec.fs, noise_ratio=nr)
        except Exception:
            o = None
        pred = (lab.get(o["classification"], "?")
                if o and o.get("assessable") and o.get("classification") else "n/a")
        grid[(t, pred)] += 1

    preds = ["NORM", "1AVB", "2AVB", "3AVB", "n/a"]
    print(f"\nAV CONDUCTION vs LUDB diagnoses\n")
    print(f"{'truth':>7} {'n':>5} | " + " ".join(f"{p:>5}" for p in preds))
    for t in ("NORM", "1AVB", "2AVB", "3AVB", "AF"):
        if not tot[t]:
            continue
        print(f"{t:>7} {tot[t]:>5} | " + " ".join(f"{grid[(t,p)]:>5}" for p in preds))
    fp = grid[("NORM", "3AVB")]
    print(f"\nfalse 'Third-degree AV Block' on normal records: {fp}/{tot['NORM']}"
          f" ({100*fp/max(tot['NORM'],1):.0f}%)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="intervals",
                    choices=["intervals", "avblock"])
    ap.add_argument("--data", default=os.path.expanduser("~/ecg-reference"))
    ap.add_argument("--fetch", action="store_true", help="download LUDB first")
    a = ap.parse_args()
    if a.fetch:
        fetch(a.data)
    d = os.path.join(a.data, "ludb")
    if not os.path.exists(d):
        sys.exit(f"no data in {d} — run with --fetch")
    (cmd_intervals if a.cmd == "intervals" else cmd_avblock)(d)
