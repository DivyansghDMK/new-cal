# PENDING CLINICAL SIGN-OFF — AV conduction labels

**Prepared for:** Dr. Razzakur Rahman, MD (Lt Col, Retd.)
**Date:** 30 August 2026
**Decision requested:** whether any of five AV conduction labels may be printed
**Status:** implemented; **validated against LUDB and NOT yet fit to print** — see §Recommendation

---

## What is being asked

Five labels are now producible by the device:

- Normal AV conduction
- First-degree AV Block
- Second-degree AV Block (Mobitz I)
- Second-degree AV Block (Mobitz II)
- Third-degree AV Block

None of them is in `REPORT_ALLOWED_CONCLUSIONS`, so none can print. That list
exists because rhythm classifiers on this device previously produced dangerous
false labels — a normal 65 bpm sinus ECG was reported as *"Ventricular
Fibrillation"*, and a tracing with a fixed 147 ms PR and a regular 910 ms RR was
reported as *"Second-degree AV Block (Mobitz I)"*. Nothing joins that list on the
strength of an implementation alone.

## Why the existing measurement could not do this

The report's PR interval is measured on the **median beat** — one averaged
complex. That is the right answer for *"what is this patient's PR interval"*, and
it stays the header value. It cannot answer the AV blocks, which are defined by
how conduction changes **from beat to beat**:

| | Defined by |
|---|---|
| 1° | every P conducts, PR fixed and > 200 ms |
| 2° Mobitz I | PR lengthens progressively, then one P is dropped |
| 2° Mobitz II | PR fixed, then one P is suddenly dropped |
| 3° | P and QRS independent — no consistent PR at all |

Averaging destroys exactly what separates them. A Wenckebach cycle of
160 / 200 / 240 / dropped averages to an unremarkable ~200 ms.

`src/ecg/metrics/av_conduction.py` measures P onset → QRS onset **per beat**.

## Evidence — synthetic

Four constructed cases, thresholds from your reference deck:

| Case | Detected as |
|---|---|
| PR 160 ms, every beat conducted | Normal AV conduction |
| PR 260 ms fixed, every beat conducted | First-degree AV Block |
| PR 160 / 200 / 240 then dropped | Second-degree AV Block (Mobitz I) |
| PR 180 ms fixed, then dropped | Second-degree AV Block (Mobitz II) |

**4 of 4.**

## Evidence — this device, superseded

An earlier run over 116 of our own recordings reported 101 not assessable (87%)
and no blocks at all. That was produced by a version carrying both defects
described below, and the 87% refusal rate was wrongly read as a signal-quality
problem on our recordings. The current figures are in the next section.

## Evidence — full validation, 763 records across three datasets

Three datasets, all 12-lead and all **500 Hz**, the same as this device.

| Dataset | n | Truth |
|---|---|---|
| **LUDB** (physionet.org/content/ludb/1.0.1) | 200 | P/QRS/T boundaries annotated per lead per beat by two cardiologists, plus a diagnosis per record. Schiller Cardiovit AT-101. |
| **PTB-XL** (physionet.org/content/ptb-xl/1.0.3) | 324 | Cardiologist report per record, SCP-coded. Selected: all 2AVB and 3AVB available, 150 1AVB, 150 clean NORM. Atrial fibrillation and flutter excluded. |
| **This device** | 239 | none — our own recordings, no reference label |

### First run (all 200 LUDB, not the 30-record sample)

The 30-record sample had shown 2 false third-degree calls out of 15 controls.
On the full set the rate is far worse:

| LUDB truth | n | → NORM | 1AVB | 2AVB | **3AVB** | n/a |
|---|---|---|---|---|---|---|
| Normal | 167 | 94 | 2 | 0 | **55** | 16 |
| 1st degree | 10 | 4 | **2** | 0 | 3 | 1 |
| 3rd degree | 5 | 0 | 0 | 0 | **3** | 2 |
| Atrial fibrillation | 18 | 1 | 0 | 2 | **8** | 7 |

| PTB-XL truth | n | → NORM | 1AVB | 2AVB | **3AVB** | n/a |
|---|---|---|---|---|---|---|
| Normal | 150 | 68 | 0 | 0 | **77** | 5 |
| 1st degree | 150 | 31 | **11** | 3 | **95** | 10 |
| 2nd degree | 11 | 2 | 0 | **3** | 4 | 2 |
| 3rd degree | 13 | 0 | 0 | 1 | **5** | 7 |

**33% of normal LUDB records and 51% of normal PTB-XL records were labelled
"Third-degree AV Block".** Complete heart block is the most serious label of the
five. On our own 239 recordings the same rule fired 26 times, and on this evidence
essentially all of them are false.

Atrial fibrillation has no P waves at all and cannot be an AV-block question, yet
8 of 18 AF records were called third-degree.

### Two distinct defects

**1. The third-degree rule uses the PR *range*.** `rng > 80.0` is
max-minus-min across ~10 beats, so a single mis-detected P fires it. LUDB record 27:

```
PR = [168, 168, 170, 174, 176, 180, 184, 184, 356]   range 188, MAD 8
```

Eight beats within 16 ms and one outlier — reported as complete heart block.

**No robust statistic rescues this rule.** Substituting the interquartile range:

| | still fires on false positives | keeps true detections |
|---|---|---|
| IQR > 40 ms | 32 / 55 | 1 / 3 |
| IQR > 60 ms | 28 / 55 | 0 / 3 |
| IQR > 80 ms | 23 / 55 | 0 / 3 |

There is no threshold that separates them, because PR variability is not what
third-degree block is. The rule has to be **removed**, not tuned. A real
implementation compares the **atrial rate against the ventricular rate**.

**2. PR still pinned to the search-window edge — the defect this document
already claimed was fixed.** The P *peak* was guarded against the window edges,
but the *onset* walk-back was not: on a drifting baseline it never meets its
threshold and runs to the window start, so the PR comes out as the window width
(360 ms) wherever the peak was. Measured before the fix:

| | records with ≥1 edge-pinned PR | beats pinned |
|---|---|---|
| LUDB | 55 / 191 | 106 / 1751 (6.1%) |
| This device | 20 / 205 | 51 / 2125 (2.4%) |

The unit tests did not catch it because synthetic strips have a flat baseline
between beats and real recordings do not. **Fixed** — the onset must now settle
inside the window or the beat contributes no PR.

### After the onset fix

| LUDB truth | n | → NORM | 1AVB | 2AVB | **3AVB** | n/a |
|---|---|---|---|---|---|---|
| Normal | 167 | 104 | 2 | 0 | **41** | 20 |
| 1st degree | 10 | 5 | **2** | 0 | 2 | 1 |
| 3rd degree | 5 | 0 | 1 | 0 | **2** | 2 |

| PTB-XL truth | n | → NORM | 1AVB | 2AVB | **3AVB** | n/a |
|---|---|---|---|---|---|---|
| Normal | 150 | 84 | 0 | 0 | **57** | 9 |
| 1st degree | 150 | 38 | **12** | 2 | **84** | 14 |
| 3rd degree | 13 | 1 | 0 | 1 | **3** | 8 |

False third-degree calls fell from 55 to 41 on LUDB and 77 to 57 on PTB-XL, and
on our own recordings from 26 to 14. **That is the onset defect being repaired,
not the classifier becoming safe** — 25% of normal LUDB and 38% of normal PTB-XL
records are still called complete heart block, because defect 1 is untouched.

## Third-degree AV Block has been REMOVED from the module

The rule is gone, not adjusted. In its place the module refuses: a PR that is not
fixed, with no dropped beat, now returns no classification and a reason saying
the atrial rate would be needed to tell dissociation from P wave mis-detection.

A wandering PR deliberately does **not** fall through to "Normal AV conduction"
either — that would be the same error in the opposite, quieter direction. Normal
conduction is a claim that every P conducted at a *consistent* interval.

### After removal

| LUDB truth | n | → NORM | 1AVB | 2AVB | 3AVB | n/a |
|---|---|---|---|---|---|---|
| Normal | 167 | 59 | 2 | 0 | **0** | 106 |
| 1st degree | 10 | 3 | 2 | 0 | **0** | 5 |
| 3rd degree | 5 | 0 | 1 | 0 | **0** | 4 |
| Atrial fibrillation | 18 | 0 | 0 | 2 | **0** | 16 |

| PTB-XL truth | n | → NORM | 1AVB | 2AVB | 3AVB | n/a |
|---|---|---|---|---|---|---|
| Normal | 150 | 43 | 0 | 0 | **0** | 107 |
| 1st degree | 150 | 0 | 12 | 2 | **0** | 136 |
| 2nd degree | 11 | 0 | 0 | 3 | **0** | 8 |
| 3rd degree | 13 | 0 | 0 | 1 | **0** | 12 |

**Zero false third-degree calls anywhere.** On our own 239 recordings it fell
from 26 to 0.

The cost is refusal: 66% of LUDB and 81% of PTB-XL now return "not assessable".
That is the honest number. Everything the old rule was confidently wrong about
now declines to answer, which is the correct behaviour for a device.

Four regression tests pin this — including one that greps the module for a new
assignment of the label.

## Second-degree AV Block has been REMOVED too

Against the only real second-degree data available — 11 PTB-XL records — Mobitz I
and II scored **3 right against 5 wrong**:

| | called | truth |
|---|---|---|
| LUDB 51, 83 | Mobitz I | **atrial fibrillation** |
| PTB-XL 00833, 04366 | Mobitz I | 1st degree |
| PTB-XL 15368 | Mobitz I | 3rd degree |
| PTB-XL 01222, 08048, 10300 | Mobitz I/II | 2nd degree ✓ |

The textbook guard was tried and **does not work**. Second-degree block has a
regular RR apart from the pause and atrial fibrillation is irregularly irregular,
so RR regularity looks like the discriminator. Measured, the ordering is inverted:

```
true second-degree   RR CoV  0.560, 0.746, 0.764
false calls          RR CoV  0.340, 0.397, 0.437     (the AF pair: 0.285, 0.287)
```

The true cases are *more* irregular, because they drop several beats rather than
one. No threshold in that ordering separates them.

A pause is now reported as a pause. Deciding **why** a beat was not conducted
needs P-P regularity measured across the pause independently of the QRS, which
this module does not do.

## Where the module now stands

It produces exactly three outcomes: `Normal AV conduction`, `First-degree AV
Block`, or nothing with a stated reason.

| LUDB truth | n | → NORM | 1AVB | any other block | n/a |
|---|---|---|---|---|---|
| Normal | 167 | 59 | **2** | 0 | 106 |
| 1st degree | 10 | 3 | 2 | 0 | 5 |
| 3rd degree | 5 | 0 | **1** | 0 | 4 |
| **Atrial fibrillation** | 18 | 0 | 0 | **0** | **18** |

| PTB-XL truth | n | → NORM | 1AVB | any other block | n/a |
|---|---|---|---|---|---|
| Normal | 150 | 43 | **0** | 0 | 107 |
| 1st degree | 150 | 0 | 12 | 0 | 138 |
| 2nd degree | 11 | 0 | 0 | 0 | 11 |
| 3rd degree | 13 | 0 | 0 | 0 | 13 |

Every atrial fibrillation record now refuses, where 8 were previously called
complete heart block. Three false `First-degree AV Block` calls remain on LUDB
and none on PTB-XL.

66% of LUDB and 83% of PTB-XL now return "not assessable", and on our own
recordings 35%.

## Recommendation: approve nothing

The earlier recommendation to approve first-degree and normal is **withdrawn**.

1. **Third-degree AV Block must be deleted from the module**, not adjusted. It is
   wrong on a quarter to a half of all normal recordings, and no threshold on PR
   variability fixes it. Rebuild it around atrial rate versus ventricular rate,
   or leave the device unable to report it.
2. **First-degree agreement is 2/10 (LUDB) and 12/150 (PTB-XL).** Even setting
   aside the beats stolen by the third-degree rule, the PR reads 182–212 ms on
   records the cardiologists called first-degree. Either the measurement is
   systematically short against the reference, or the 200 ms threshold cannot be
   applied to it as it stands.
3. **Atrial fibrillation must be excluded before any AV-conduction claim.** No P
   waves means the question does not apply; today it produces a block label.
4. **Second-degree** is 3/11 on PTB-XL, the only real Mobitz data available.
   LUDB contains no Mobitz cases at all.

## What to do next

- Delete the third-degree rule, or rebuild it on atrial versus ventricular rate.
- Refuse any record whose rhythm is atrial fibrillation or flutter.
- Use LUDB's per-beat P and QRS boundary annotations as ground truth for the PR
  measurement itself rather than comparing classifications — that isolates
  whether the 10–20 ms gap is in P onset detection, QRS onset detection, or both.
- Add a real-baseline regression test. Both defects above survived a passing
  15-test suite because every test strip had a flat baseline.

## The false positives this nearly shipped with

The first version produced **four "First-degree AV Block" findings** on these same
116 recordings — three of them reading **PR = 360 ms** on tracings whose printed
PR was 142–171 ms.

The cause: when no P wave exists in the search window, taking the largest value in
that window returns whatever sits at its boundary, and 360 ms is the boundary.
The fix requires a genuine local peak clear of both window edges. After it: the
four synthetic blocks are still detected, and the false positives are gone.

This is recorded because it is the same failure class the allow-list exists to
prevent, and it was reproduced from a different cause. It is the reason for the
refusal counts above rather than a confident answer on every strip.

## What this cannot do, and should not be asked to

- **A 10-second strip is short.** At 60 bpm it holds ~10 beats. A Wenckebach
  cycle can be 3–4 beats, so one strip may hold two cycles, one, or a fragment.
  **Mobitz II can be entirely absent** from a 10 s window in a patient who has it.
  The module reports what it sees and never infers absence.
- **Signal quality is a separate issue, and was wrongly blamed.** 72 of the 116
  reports have at least one lead over the muscle-filter noise limit, and electrode
  prep is worth doing on its own merits — but LUDB proved it was not the cause of
  the refusal rate. Clean reference recordings refused at the same 87%.
- **Third-degree block needs the atrial rate to exceed the ventricular rate.**
  The current rule infers dissociation from PR variability alone, and the
  validation above shows what that costs: a quarter to a half of all normal
  recordings labelled complete heart block. It is not a limitation to disclose,
  it is a rule to remove.

## What would print

```
1. First-degree AV Block ················· PR 302, > 200mS
   - conduction delay at the AV node
```

The criterion and the implication follow the same format as the existing box.

## Files

| | |
|---|---|
| Implementation | `src/ecg/metrics/av_conduction.py` |
| Tests (15, all passing) | `tests/test_av_conduction.py` |
| Allow-list (unchanged) | `ecg_report_generator.py:1689` |

A test asserts these labels are **absent** from the allow-list, so adding one
without revisiting this document will fail the suite.
