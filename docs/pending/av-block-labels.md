# PENDING CLINICAL SIGN-OFF — AV conduction labels

**Prepared for:** Dr. Razzakur Rahman, MD (Lt Col, Retd.)
**Date:** 30 August 2026
**Decision requested:** whether any of five AV conduction labels may be printed
**Status:** implemented and tested; **nothing reaches a report**

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

## Evidence — 116 real recordings from this device

| Result | Count |
|---|---|
| **Not assessable** | **101 (87%)** |
| Normal AV conduction | 15 |
| Any AV block | **0** |

Why the 101 were refused:

| Reason | Count |
|---|---|
| P wave not found on enough beats | 72 |
| Lead II too noisy (ratio > 0.030) | 25 |

Where a PR could be measured, it agrees with the PR the report already prints:
median difference **−6 ms**, within 20 ms on **13 of 15**.

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
- **87% of current recordings are not assessable**, mostly because the P wave
  cannot be found. That traces back to signal quality: 72 of these 116 reports
  have at least one lead over the muscle-filter noise limit. Electrode prep will
  move this number more than any algorithm change.
- **Third-degree block needs the atrial rate to exceed the ventricular rate**, and
  a 10 s strip may not settle that. The current rule infers dissociation only from
  a PR that is neither fixed nor progressive, which is weaker than the full
  criterion. If this label is approved it should carry that limitation.

## Options

1. **Approve `First-degree AV Block` only.** PR > 200 ms fixed is the simplest and
   safest of the five — one threshold on a measurement the report already prints
   and already trusts.
2. **Approve `Normal AV conduction` as well**, so a clean strip states positively
   that conduction was checked. This is the only one that carries no false-positive
   risk.
3. **Hold the 2° and 3° labels** until a longer recording path exists, or until
   the not-assessable rate falls with better acquisition.
4. **Approve none**, and keep the module as a measurement only.

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
