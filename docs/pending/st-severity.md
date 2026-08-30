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

## The ST measurement is the real problem

Across 1607 lead measurements on records with no ischemia label:

```
median  -0.10 mm      IQR  -0.40 .. +0.30      |ST| > 0.5 mm on 34% of leads
```

A healthy lead should sit near 0.00 mm. What fires:

| | records |
|---|---|
| ST depression | 109 |
| ST elevation (no territory) | 46 |
| ST elevation, named territory | 9 |

### Two things already ruled out

**Restricting severity to the territorial STEMI patterns.** Territorial findings
fire on 6% of the no-ischemia records against 4% of the STEMI records. That is
chance, so specificity cannot be bought this way.

**The J point.** `measure_st_deviation_from_median_beat()` places it at the
**S-wave nadir** — `argmin` over R+20…60 ms — rather than where the QRS returns
to baseline, which looked like the obvious cause. Re-measured against the real
QRS offset from `detect_qrs_offset_slope_assisted()`, the scatter got slightly
**worse**: 41% of leads over 0.5 mm against 34%. The J point is not the cause.

The J-point definition is still wrong and should be corrected on its own merits.
It is not what is driving this.

### What has not been ruled out

- **The TP baseline.** Every ST value is a difference from it, so if it is noisy
  or lands on the wrong segment, the whole distribution scatters. This is the
  next thing to test, using LUDB's annotated T offsets and P onsets to place a
  known-good TP segment and comparing.
- **The mV scale.** `measure_st_deviation_from_median_beat()` hardcodes
  `adc_to_mv = 1200.0` while the waveform path uses 1184 and the RV5/SV1 path
  uses 2048/1441. Which is correct is still unresolved and needs the bench
  calibration — 1 mV into a limb channel and a chest channel. Until then no
  threshold in mm can be trusted, including these.

## Decision requested

Nothing to approve yet. This records that the defect is real, that the fix is
ready, and that shipping it now would be a regression. The order of work is:

1. Bench calibration, so mm means millimetres.
2. Diagnose the ST scatter — TP baseline first.
3. Correct the J point.
4. Then wire severity to the clinical findings, and re-validate on these same
   records.
