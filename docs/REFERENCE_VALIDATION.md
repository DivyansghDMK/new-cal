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

## Result 1 — QRS duration read 18 ms short: FOUND AND FIXED

Measured through `calculate_all_ecg_metrics()`, the function that fills the
report header, against the cardiologist boundaries on the same records:

| | n | our median | reference median | bias | median abs err | ≤10 ms | ≤20 ms |
|---|---|---|---|---|---|---|---|
| PR | 172 | 160 ms | 160 ms | −2 ms | 14 ms | 41% | 66% |
| **QRS (was)** | 195 | **74 ms** | **93 ms** | **−18 ms** | 18 ms | 27% | 54% |
| QT | 195 | 400 ms | 398 ms | +1 ms | 22 ms | 32% | 46% |

PR and QT were unbiased. QRS was not — a reference median of 93 ms is textbook
for a mixed population, and ours read 74 ms, below the normal range entirely.

### Isolating it

Comparing our per-beat borders against the cardiologist's, in Lead II, over
1806 beats:

| | bias | IQR |
|---|---|---|
| QRS **onset** | **+12 ms** (starts too late) | +6 … +16 |
| QRS **offset** | **−8 ms** (ends too early) | −16 … 0 |
| QRS width | −20 ms | −32 … −8 |

Both borders err *inward*. That is not a tuning problem — it is what a
**single lead** looks like. A single lead sees one projection of the
depolarisation wavefront, so the earliest deflection and the latest return to
baseline both happen in *other* leads.

The codebase already knew this. `qrs_detection.py` implements
`compute_global_qrs_duration_12lead()` — the Glasgow/Marquette boundary rule,
earliest onset to latest offset across the lead set — and its own comment says
single-lead delineation "typically reads 10-20 ms short". Run directly on these
records it measures **93 ms against the reference's 93 ms**.

### The cause

```python
GLOBAL_QRS_ENABLED = os.getenv("ECG_GLOBAL_QRS", "") in {"1","true","yes","on"}
```

The default was the empty string, so this was **False**. The multi-lead path was
behind an environment variable nothing sets, and every unit in the field measured
QRS from Lead II alone. Across all 200 LUDB records `qrs_method` came back
`single-lead` 200 times and `qrs_leads_used` was 1 every time, with 12 leads
passed in.

### After enabling it

| | median | reference | bias | median abs err | ≤10 ms | ≤20 ms |
|---|---|---|---|---|---|---|
| single-lead (was) | 74 ms | 93 ms | −18 ms | 18 ms | 27% | 54% |
| **global multi-lead (now)** | **93 ms** | 93 ms | **+1 ms** | **7 ms** | **63%** | **84%** |

195 of 200 records took the multi-lead path; 5 fell back, which is the intended
behaviour when too few leads delineate.

**The `Wide QRS` conclusion is the point.** It triggers at 120 ms, and an 18 ms
short read hid it. With the global path on, 11% of LUDB records measure ≥ 120 ms —
**exactly matching the 11% the cardiologists call wide**.

**Fixed** in `src/ecg/ecg_calculations.py`: the default is now `"1"`. Set
`ECG_GLOBAL_QRS=0` to restore the old single-lead behaviour.

**For Dr. Rahman:** this changes the printed QRS value on every report, and with
it how often `Wide QRS` appears. It is not a new threshold — the 120 ms criterion
is unchanged — it is the measurement being taken across the lead set instead of
one lead, which is what every 12-lead cart does. The evidence is the table above.

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
