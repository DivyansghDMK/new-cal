# Validating this device against cardiologist-annotated data

## Why we needed outside data

Our own recordings carry no truth label. Nothing measured on them can be checked,
because a rule that is wrong on every strip looks exactly like a rule that is
right on every strip. That is not a hypothetical: the AV conduction module was
run over 116 of our own recordings, produced no blocks at all, and that was read
as evidence it was safe. It was labelling a third of all normal ECGs as complete
heart block, and our data could not show it.

Two public datasets fix this. Both are 12-lead at **500 Hz** — the same
acquisition as this device.

| | n | What the truth is |
|---|---|---|
| **LUDB** [physionet.org/content/ludb/1.0.1](https://physionet.org/content/ludb/1.0.1/) | 200 | Two cardiologists annotated P, QRS and T **onset, peak and offset, per lead per beat**, plus a diagnosis per record. Recorded on a Schiller Cardiovit AT-101. |
| **PTB-XL** [physionet.org/content/ptb-xl/1.0.3](https://physionet.org/content/ptb-xl/1.0.3/) | 21799 | An SCP-coded cardiologist report per record. No per-beat boundaries, but far more pathology — including the Mobitz cases LUDB has none of. |

LUDB's per-beat boundaries are the valuable part: they are ground truth for
exactly the interval numbers the report header prints.

```
python tools/validate_against_reference.py --fetch --data ~/ecg-reference
python tools/validate_against_reference.py --data ~/ecg-reference intervals
python tools/validate_against_reference.py --data ~/ecg-reference avblock
```

`pip install wfdb` — but keep **numpy < 2**. Installing wfdb pulls numpy 2.x,
which breaks matplotlib 3.7 with `ImportError: numpy.core.multiarray failed to
import` and stops PDF generation. `pip install "numpy<2"` restores it.

## Result 1 — QRS duration reads about 18 ms short

Measured through `calculate_all_ecg_metrics()`, the function that fills the
report header, against the cardiologist boundaries on the same records:

| | n | our median | reference median | bias | median abs err | ≤10 ms | ≤20 ms |
|---|---|---|---|---|---|---|---|
| PR | 172 | 160 ms | 160 ms | **−2 ms** | 14 ms | 41% | 66% |
| **QRS** | 195 | **74 ms** | **93 ms** | **−18 ms** | 18 ms | 27% | 54% |
| QT | 195 | 400 ms | 398 ms | **+1 ms** | 22 ms | 32% | 46% |

PR and QT are unbiased. **QRS is not.** A reference median of 93 ms is textbook
for a mixed population; ours reads 74 ms, below the normal range entirely.

The same −19 ms bias appears through `measure_pr_from_median_beat` /
`measure_qrs_duration_paper`, a separate code path. Two independent
implementations agreeing on the same offset points at the shared QRS
onset/offset detection, not at either caller.

**Why it matters clinically.** `Wide QRS` triggers at 120 ms. An 18 ms short read
means a genuine 120–135 ms QRS prints as 102–117 ms and the finding never
appears — bundle branch block and wide-complex rhythms are missed. This is the
same `Wide QRS` label already flagged as questionable in the conclusion box.

**Not yet fixed.** Where the 18 ms is lost — onset, offset, or both — needs to be
isolated against the LUDB boundaries before anything is changed, and a threshold
that decides a printed conclusion needs Dr. Rahman's sign-off.

## Result 2 — the AV conduction module labels normal ECGs as complete heart block

| LUDB truth | n | → NORM | 1AVB | 2AVB | **3AVB** | n/a |
|---|---|---|---|---|---|---|
| Normal | 167 | 94 | 2 | 0 | **55 (33%)** | 16 |
| 1st degree | 10 | 4 | 2 | 0 | 3 | 1 |
| 3rd degree | 5 | 0 | 0 | 0 | 3 | 2 |
| Atrial fibrillation | 18 | 1 | 0 | 2 | **8** | 7 |

On PTB-XL the false rate was **51%** of 150 normal records. Full analysis, both
root causes, and the withdrawn sign-off recommendation are in
[`docs/pending/av-block-labels.md`](pending/av-block-labels.md).

Atrial fibrillation has no P waves and cannot be an AV-conduction question at
all, yet 8 of 18 AF records were called third-degree.

## Result 3 — a defect a passing test suite could not see

PR intervals were pinning to the P search-window edge (360 ms) on **55 of 191**
LUDB records and 20 of 205 of our own. The P *peak* was guarded against the
window edges; the *onset* walk-back was not, so on a drifting baseline it ran to
the window start. Fixed.

It survived a passing 15-test suite because every synthetic test strip has a flat
baseline between beats and real recordings do not. **Any regression test for wave
boundary detection has to run on real recordings**, and this tool is how.

## What else these datasets can check

Both carry labels for things the device already reports, none of which has been
validated yet:

- **LVH** — 108 LUDB records; tests the Sokolow-Lyon index and the RV5/SV1
  amplitude path, including the open question about the 2048/1441 vs 1184
  divisors and the lead II / V2 calibration disagreement.
- **ST elevation and STEMI** — 51 LUDB records with ischemia, 8 anterior and 8
  septal STEMI; tests the age/sex ST thresholds and the `classify()` bug where a
  STEMI still returns NORMAL ECG.
- **Electrical axis** — LUDB labels it per record; `axis` is computed but never
  drawn.
- **Atrial fibrillation, extrasystoles, RBBB/LBBB** — every rhythm and conduction
  label in the conclusion box.

The device's own 239 reports have a QRS IQR of 94–99 ms and a PR IQR of
153–166 ms across all of them, which is far too narrow to be a population — they
are repeat recordings of a few subjects. They cannot substitute for this.
