# What this device can and cannot detect, measured

Every number here is measured against **LUDB** — 200 records, 12-lead, 500 Hz,
with P/QRS/T boundaries annotated per lead per beat by two cardiologists and a
diagnosis per record. Reproduce with:

```
python tools/validate_against_reference.py --data ~/ecg-reference intervals
```

Eight conclusions can print (`REPORT_ALLOWED_CONCLUSIONS`). Here is how each one
actually performs.

---

## ✅ Trustworthy

### QRS duration — the measurement

| | n | ours | reference | bias | median err | ≤10 ms |
|---|---|---|---|---|---|---|
| QRS | 195 | 93 ms | 93 ms | **+1 ms** | **7 ms** | 63% |
| PR | 172 | 160 ms | 160 ms | −2 ms | 14 ms | 41% |

Both unbiased. QRS became trustworthy only after the multi-lead boundary was
enabled — it read 18 ms short before that.

### `Wide QRS` / `Narrow QRS` / `Borderline QRS duration`

**161 of 195 records agree with the cardiologist's own boundaries (83%).**

| cardiologist ↓ | → Narrow | Borderline | Wide | Short |
|---|---|---|---|---|
| Narrow | **141** | 7 | 4 | 2 |
| Borderline | 8 | **3** | 2 | 0 |
| **Wide** | 5 | 0 | **16** | 0 |
| Short | 5 | 1 | 0 | **1** |

`Wide QRS` catches **16 of 21** genuinely wide records with 6 false positives.
That is the strongest label the device has, and it detected none of them before
this week.

`Borderline QRS duration` is weak — 3 of 13 — because a 10 ms band sits inside
the measurement's own 7 ms error.

---

## ⚠️ Weak — prints, but misses most of what it should catch

### `Prolonged QTc` — misses 19 of 23

| | |
|---|---|
| cardiologist says prolonged | 23 records → **4 caught, 19 missed** |
| cardiologist says normal | 172 records → 162 correct, 10 false |

Overall "agreement" reads 166/195 (85%), which is misleading: it is high only
because most records are normal. **The label finds 17% of real QT prolongation.**
The QT measurement itself is unbiased (+1 ms) but scatters (22 ms median error),
and QTc squares that through the Bazett division.

Do not rely on this label to exclude long QT.

### `Normal Sinus Rhythm` — 73 of 153

| cardiologist ↓ | result |
|---|---|
| Sinus rhythm (153) | 73 Normal Sinus, 11 Bradycardia, **13 called Atrial Fibrillation**, 56 Undetermined |
| Sinus bradycardia (25) | **10** Bradycardia, 14 Undetermined, 1 Atrial Fibrillation |
| Sinus tachycardia (4) | **0** — 3 called Normal Sinus, 1 Undetermined |

37% of ordinary sinus rhythms come back "Undetermined Rhythm", which is not in
the allow-list, so **the conclusion box prints nothing at all** for those.

### `Sinus Bradycardia` — 10 of 25. `Sinus Tachycardia` — 0 of 4.

Rate thresholds are simple arithmetic, so this is not a threshold problem: the
rhythm engine requires `p_present and np.std(rr) < 0.1` before it will name any
sinus rhythm, and that gate is what is failing.

---

## 🔴 Do not rely on — known defective

### Atrial fibrillation is not reliably separated from sinus rhythm

**13 of 153 sinus records were called Atrial Fibrillation**, and in the dangerous
direction **1 AF and 2 atrial flutter records were called Normal Sinus Rhythm or
Sinus Tachycardia**.

AF is not in the allow-list so it never prints — but the misclassification
suppresses the rhythm label that *should* have printed, which is where the 56
"Undetermined" come from.

### ST elevation and depression — the rule is incomplete

The measurement is sound: at LUDB's own calibration with the cardiologists' own
landmarks, ST reads median −0.17 mm, IQR −0.45…+0.12.

The **rule** fires an ST finding on **114 of 149 records with no ischemia label
(77%)**, because ST depression requires only ONE lead below −0.5 mm — no
contiguity requirement, and no slope requirement. See
[`docs/pending/st-severity.md`](pending/st-severity.md).

Consequently a STEMI still prints `NORMAL ECG` as its overall reading, and the
one-line fix for that cannot ship until the ST rule is corrected.

### AV blocks — nothing beyond first degree

Second- and third-degree were removed after validation; the module now produces
only `Normal AV conduction`, `First-degree AV Block`, or a refusal, and **none of
the three prints**. First degree agrees on 2 of 10.
See [`docs/pending/av-block-labels.md`](pending/av-block-labels.md).

---

## Never validated

Nothing below has been checked against reference data at all:

| | available truth |
|---|---|
| **LVH / Sokolow-Lyon** | 108 LUDB records. Blocked on the bench calibration — RV5/SV1 divide by 2048/1441 while the waveform uses 1184. |
| **Electrical axis** | LUDB labels it per record. The P/QRS/T axes *are* printed in the header; what is missing is any axis *interpretation* — no "left axis deviation" statement exists, and the printed numbers have never been checked against the reference. |
| **Bundle branch block** | 29 incomplete RBBB, 4 complete LBBB. `detect_bundle_branch_block()` is untested. |
| **Extrasystoles (PVC/PAC)** | 14 LUDB records, 6 single PVC, 4 single PAC. |
| **Hyperkalaemia** | no reference data identified. |

---

## Not printed at all, though it is computed

`build_interpretation()` returns a `severity` of `NORMAL ECG` / `BORDERLINE ECG` /
`ABNORMAL ECG` / `UNINTERPRETABLE ECG`. **Nothing in the report renderer reads it.**
Every commercial cart prints an equivalent line. Ours computes one and drops it.

That is separate from the defect in [`pending/st-severity.md`](pending/st-severity.md),
which is about the value being wrong when it *is* read.

## Honest summary

One label is genuinely good — **`Wide QRS`, and only since the multi-lead QRS
boundary was switched on**. `Narrow QRS` is reliable mostly because most people
are narrow.

Everything else either misses most of what it should catch (`Prolonged QTc`, the
sinus labels) or is blocked behind a defect that is now written down. The device
is far more likely to print **nothing** than to print something wrong, which is
the safer of the two failure modes — but it is not the same as working.
