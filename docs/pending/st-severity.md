# PENDING — the ST measurement, and why "NORMAL ECG" still prints on a STEMI

**Prepared for:** Dr. Razzakur Rahman, MD (Lt Col, Retd.)
**Status:** defect confirmed, fix written and tested, **deliberately not shipped**

---

## The defect

A tracing with 2.5 mm of ST elevation across V2–V4 and an ordinary sinus rhythm
prints, **on the same sheet**:

```
ST elevation, anterior leads ······· ST >0.10mV, V2 V3 V4
Normal Sinus Rhythm ················ V-rate 72, 60-100
Narrow QRS ························· QRSD 92, < 110mS

                                     NORMAL ECG
```

`build_interpretation()` computes severity as `classify(kept)` — the rhythm
engine's findings alone. ST deviation is measured per lead and merged into the
statement list separately, so it never reaches the classifier. Neither does the
wide-complex tachycardia caution.

## The fix, and why it is not in the build

Changing `classify(kept)` to classify every clinical statement is one line. It
was written, unit-tested, and validated on LUDB — where it moved 19 of 28 STEMI
records from NORMAL ECG to ABNORMAL ECG, up from none.

**It also moved 114 of the 149 records with no ischemia label.**

| LUDB group | n | prints an ST finding |
|---|---|---|
| STEMI | 28 | 19 (68%) |
| Other ischemia | 22 | 20 (91%) |
| **No ischemia label** | **149** | **114 (77%)** |

Wiring severity to that would print ABNORMAL ECG on three quarters of normal
people, which is worse than the defect it fixes.

## What is actually wrong: the rule, not the measurement

The ST measurement was suspected and has now been cleared. Measured on lead II
across 929 beats of the 149 LUDB records with no ischemia label, **at LUDB's own
calibration and using the cardiologists' own P/QRS/T boundaries**:

```
median  -0.17 mm      IQR  -0.45 .. +0.12      |ST| > 0.5 mm on 28% of beats
```

That is what a real population looks like. Four candidate causes were tested
against it and all four are ruled out:

| Candidate | Result |
|---|---|
| **J point** placed at the S-wave nadir instead of the QRS offset | swapping in the cardiologists' QRS offset: 31% → 32%. **No effect.** |
| **TP baseline** window placement | swapping in a TP segment bounded by the annotated T offset and P onset: 31% → 28%. **3 points.** |
| **mV scale** — the hardcoded `adc_to_mv = 1200.0` | measured at LUDB's own true calibration the distribution is unchanged. Our 1184 reproduces it to 1.3%. **Not the cause.** |
| **Contiguity** — requiring 2 leads of one territory | clean records 67% → 44%, but ischemia only 91% → 64%. Helps, nowhere near enough alone. |

The J-point definition is still wrong and worth correcting on its own merits. It
is not what is driving this.

### The rule is missing two standard criteria

```python
if depressed:                      # interpretation.py, st_findings()
    out.append(("ST depression", ...))
```

`depressed` is every lead at or below −0.5 mm. **One lead is enough.** Elevation
requires two leads of a territory before it is called territorial; depression has
no contiguity requirement at all.

The Fourth Universal Definition of MI, and your reference deck, require ST
depression to be:

1. **≥ 0.5 mm in two contiguous leads** — not implemented; measured above as
   worth 67% → 44% on the no-ischemia records.
2. **Horizontal or downsloping** — not implemented, and not even measured. This
   is the criterion that separates ischaemia from the ordinary upsloping ST
   depression a healthy heart shows at rate. It is almost certainly the larger
   half of the missing specificity, and the ST slope is not currently computed
   anywhere in the codebase.

So the fix is not in the signal chain. It is two criteria that were never
implemented, and both are clinical thresholds.

## The two criteria were implemented experimentally and measured

Not a proposal — measured on all 199 LUDB records, adding one criterion at a time.
ST slope is computed as the change from J+60 ms to J+80 ms; "not upsloping" means
that change is zero or negative.

| ST depression rule | STEMI (28) | Other ischemia (22) | **No ischemia label (149)** |
|---|---|---|---|
| **A** — any single lead ≤ −0.5 mm *(ships today)* | 50% | 91% | **65%** |
| **B** — A + two contiguous leads of one territory | 29% | 59% | 40% |
| **C** — B + horizontal or downsloping | 11% | 32% | **7%** |

Rule C is what the Fourth Universal Definition of MI actually requires.

### Sensitivity falls, and the test gets much better anyway

Rule A finds 91% of ischemia — while firing on 65% of everyone else. As a test
that is barely informative: a positive likelihood ratio of 1.4. Rule C finds 32%
while firing on 7%, a likelihood ratio of **4.6**. A finding that appears on two
thirds of healthy people carries no information; one that appears on 7% does.

ST *depression* is also not the primary criterion for STEMI — elevation is — so
the 50% → 11% column is the reciprocal-change path, not the diagnosis.

### The residual 7% is mostly not error

Of the 10 no-ischemia records still flagged under rule C, **8 carry a
hypertrophy label** and 3 also carry a non-specific repolarisation abnormality:

| record | leads | also labelled |
|---|---|---|
| 22, 77, 102, 105, 121, 147, 165, 179 | — | left atrial and/or left ventricular hypertrophy |
| 93, 122 | V1–V2, III–V5 | nothing |

LVH strain produces genuine ST depression. Those are correct findings on records
that happened to carry no *ischemia* label — LUDB codes hypertrophy in a separate
column. **The genuinely unexplained rate is 2 of 149, about 1.3%.**

So the honest expectation after the fix is roughly **97 of 149 false flags
becoming 2**, not "100% correct" — which is not available on ST from any device,
and is not what two cardiologists reading the same tracing achieve either.

### What implementing this actually costs

The contiguity test is a few lines against `ST_TERRITORIES`, which already exists.
**The slope does not exist anywhere in the codebase** and has to be added — ST at
J+60 and at J+80, per lead, carried through to `st_findings()` alongside the value.
That is new measurement code, not a threshold edit, so it needs its own tests.

## Decision requested

Nothing to approve yet. This records that the defect is real, that the fix is
ready, and that shipping it now would be a regression. The order of work is:

1. **Approve the two missing ST depression criteria** — two contiguous leads,
   and horizontal or downsloping only. Both are from your own reference deck, and
   the measured effect is in the table above: flags on no-ischemia records fall
   from 97 of 149 to 10, of which 8 are hypertrophy records showing real strain.
2. Implement the ST slope measurement, which does not exist yet, with its own
   tests, and re-validate on these 199 records.
3. Correct the J point on its own merits (S-wave nadir → QRS offset), even though
   it is not what is causing this.
4. Then wire severity to the clinical findings and re-validate.

The bench calibration is still needed for the RV5/SV1 and LVH work, but it is
**not** a blocker here: the ST distribution is the same at LUDB's true
calibration as at ours.
