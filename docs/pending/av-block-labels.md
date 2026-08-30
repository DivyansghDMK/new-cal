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

## Evidence — 116 real recordings from this device

| Result | Count |
|---|---|
| Not assessable | 101 (87%) |
| Normal AV conduction | 15 |
| Any AV block | 0 |

**This looked reassuring and was misleading.** The 87% refusal rate was read as a
signal-quality problem on our recordings. It was not — see the next section.

## Evidence — LUDB, 30 cardiologist-annotated records

The Lobachevsky University Database (physionet.org/content/ludb/1.0.1/) is 200
12-lead, 10 s, 500 Hz records from a Schiller Cardiovit AT-101, with P, QRS and T
boundaries annotated per lead per beat by two cardiologists, and a diagnosis per
record. It is the same acquisition parameters as this device, on a reference cart,
with ground truth. 30 records were used: 10 first-degree AV block, 5 third-degree,
15 clean sinus controls.

**First run — the detector failed on clean reference data.**

| | Agreement |
|---|---|
| First-degree AV block | 1 / 10 |
| Third-degree AV block | 0 / 5 |
| Clean sinus control | 2 / 15 |

26 of 30 came back "not assessable" — **the same 87% as on our own recordings**.
So the refusal rate was never about our signal quality. It was the algorithm.

The cause: the P wave's amplitude was tested against noise estimated on the search
window **that contains the P wave**, so a larger P raised its own threshold. On
record 18 the P amplitudes were 0.59–1.12 mm against a bar of 0.73–1.60 mm, and
every one failed. Fixed by estimating noise from the TP segment instead.

**Second run — after the fix.**

| | Agreement | |
|---|---|---|
| First-degree AV block | **2 / 10** | most read PR 197–212 ms, at or just under the 200 ms threshold |
| Third-degree AV block | **3 / 5** | |
| Clean sinus control | **11 / 15** | **2 false "Third-degree AV Block" on clean sinus** |
| Not assessable | 5 / 30 | down from 26 |

P wave detection is now working — found on 8–13 of 9–13 beats on most records.
**The classification is not.**

## Recommendation: approve nothing yet

The earlier recommendation (approve first-degree and normal) is **withdrawn**.

1. **First-degree agreement is 2/10.** Eight records the cardiologists called
   first-degree measure 182–212 ms here — at or below the 200 ms threshold. Either
   the PR measurement is systematically 10–20 ms short against the reference, or
   the threshold cannot be applied to this measurement as it stands. That has to be
   resolved against the LUDB per-beat annotations before any threshold is trusted.
2. **Third-degree produced 2 false positives on clean sinus records** (5 and 37),
   which is the most dangerous direction for the most serious label. The current
   rule infers dissociation from PR variability alone, which is too weak. It should
   be dropped from consideration entirely until it tests atrial rate against
   ventricular rate.
3. **Normal AV conduction** is 11/15 with the 2 false positives above counted
   against it. It is the least risky label but should wait for the same fix.

## What to do next

- Use LUDB's per-beat P and QRS boundary annotations as ground truth for the PR
  measurement itself, rather than comparing classifications. That isolates whether
  the 10–20 ms gap is in P onset detection, QRS onset detection, or both.
- Rebuild the third-degree rule around atrial-versus-ventricular rate.
- Re-validate on the full 200 LUDB records, not 30.
- LUDB contains **no Mobitz I or Mobitz II cases at all**, so those two remain
  unvalidated against real data. PTB-XL or Chapman-Shaoxing would be needed.

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
- **Third-degree block needs the atrial rate to exceed the ventricular rate**, and
  a 10 s strip may not settle that. The current rule infers dissociation only from
  a PR that is neither fixed nor progressive, which is weaker than the full
  criterion. If this label is approved it should carry that limitation.

## Options — superseded

The four options previously listed here (approve first-degree, approve normal,
hold 2nd and 3rd degree, approve none) were written before the LUDB validation.
**Approve none** is now the only supportable one, for the reasons in
§Recommendation above. The others should be reconsidered only after the PR
measurement is validated against LUDB's per-beat annotations.

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
