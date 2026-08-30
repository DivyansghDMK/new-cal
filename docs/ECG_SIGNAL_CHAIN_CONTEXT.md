# ECG Signal Chain — Working Context

**Status:** filter and report defects fixed (uncommitted); calibration open, pending bench + clinical sign-off
**Last updated:** 30 August 2026
**Scope:** filters, the J point, lead V1, amplitude calibration, and the report/JSON pipeline

This is the context record for the ECG **signal chain** — everything between the
electrode and the ink. It is a companion to
[ECG_INTERPRETATION_CONTEXT.md](ECG_INTERPRETATION_CONTEXT.md), which covers the
*clinical criteria*; this file covers the *signal*. They are separate workstreams and
neither supersedes the other.

It exists so a future session does not have to re-derive any of it. Every number below
was measured against real recordings in this repository, and the recipe for reproducing
each one is in §8.

---

## 1. Why this file exists

The investigation started from one observation: **a 12-lead report printed at the 25 Hz
muscle-filter setting looked "not clear" next to a print from a BPL cart at the same
setting.** Chasing that produced a chain of findings — some in our filters, some in the
older upstream filters, and some in the calibration and reporting plumbing that have
nothing to do with filtering at all.

Two hypotheses were raised during the investigation and later **retracted**. They are
recorded in §7.4 so they are not raised again.

---

## 2. Repositories — there are three, and they are not the same

This caused real confusion. Get it right before comparing anything.

| | Path / remote | State |
|---|---|---|
| **Working tree** | `/Users/deckmount/new/qww_new` — `origin` = `DivyansghDMK/qww_new` | **30 commits ahead** of `origin/main`, 0 behind, plus uncommitted changes. This is what runs. |
| **qww_new upstream** | `github.com/DivyansghDMK/qww_new` @ `origin/main` | The *older* code. `src/ecg/interpretation.py` does not exist there. `ecg_filters.py` is 751 lines vs 1212 locally. |
| **daweical** | `github.com/DivyansghDMK/daweical` — cloned at `~/Desktop/democardiox/clone/qww_new` | A **different repository**, HEAD `0ad99ab`, **not an ancestor** of `qww_new`'s main. Reports found on disk from `~/Desktop/democardiox/clone/` came from here. |

**Key fact:** `daweical`'s `src/ecg/ecg_filters.py` is **byte-identical** to `qww_new`
`origin/main`'s. So "the old filter" means the same module in both, and any defect in it
is shared by both upstreams.

Uncommitted in the working tree at time of writing:

```
README.md                       +407      (documentation of all of the below)
src/ecg/ecg_filters.py          +128/-…   (the filter fixes)
src/ecg/ecg_report_android.py   +25       (lead-noise reporting)
src/utils/settings_manager.py   +10/-…    (default cutoff 25 -> 150)
tests/test_filters_jpoint.py    new file  (regression suite, 12 tests)
```

A build from `HEAD` will **not** behave like the working tree. Say which you mean.

---

## 3. The signal chain — what actually runs

### 3.1 The live path

```
hardware  ->  twelve_lead_test.generate_pdf_report()
              ->  ecg_report_android.generate_report()          <-- the live renderer
                  ->  ecg_filters.apply_ecg_filters()           <-- the live filters
                      1. apply_dft_filter   (baseline / high-pass)
                      2. apply_emg_filter   (muscle / low-pass, QRS-gated)
                      3. apply_ac_filter    (mains, adaptive LMS)
                  ->  interpretation.build_interpretation()     <-- the conclusion box
```

`src/dashboard/analysis_window.py:3202` is the other caller of `generate_report`.

### 3.2 The generators, and which are dead

| File | Lines | Callers | Live? |
|---|---|---|---|
| `ecg_report_android.py` | 1241 | 3 | **YES — this draws the 12-lead PDF** |
| `interpretation.py` | ~313 | live | **YES — supplies the conclusion box** |
| `ecg_report_generator.py` | 4756 | 7 | Partly. Its **allow-list helpers are imported and live**; its own `generate_ecg_report()` ReportLab renderer is **never called** by the 12-lead path. |
| `hrv_ecg_report_generator.py` | 4942 | 1 | Separate module, separate box |
| `hyperkalemia_ecg_report_generator.py` | 4258 | 1 | Separate module, separate box |
| `6_2_ecg_report_generator.py` | 4157 | **0** | **Dead code** |
| `4_3_ecg_report_generator.py` | 1 | 0 | Empty stub |

**This distinction has already caused a real bug.** The conclusion allow-list was
originally applied only in `ecg_report_generator.generate_ecg_report()`, which the
12-lead page never calls — so `Asystole` kept printing after the restriction was
supposedly in place. It is now applied in `twelve_lead_test.py` before the hand-off, and
pinned by `TestAndroidReportPathIsFiltered` in `tests/test_report_conclusions.py`.

### 3.3 The device has EIGHT real channels, not twelve

Measured across 25 reports: the augmented and third limb leads are **derived in software**
from I and II, not independently acquired.

| lead | identity | max \|error\| | as % of lead II span |
|---|---|---|---|
| III | `II - I` | **0.00 ADC** | 0.000% |
| aVR | `-(I+II)/2` | 0.50 ADC | 0.023% |
| aVL | `I - II/2` | 0.50 ADC | 0.023% |
| aVF | `II - I/2` | 0.50 ADC | 0.023% |

The 0.50 ADC on the augmented leads is exactly the rounding of the `/2`. III is bit-exact.

**Why this matters:** the real front-end channels are **I, II, V1, V2, V3, V4, V5, V6**.
A per-channel gain error cannot exist among III/aVR/aVL/aVF — but the calibration
discrepancy in §7.1 is between **lead II and V2**, which *are* two physically separate
amplifier channels. That makes it a legitimate hardware candidate and it is testable on
the bench: inject a known 1 mV into a limb channel and a chest channel separately and
compare.

### 3.4 Current filter constants — `src/ecg/ecg_filters.py`

| Constant | Line | Value | Note |
|---|---|---|---|
| `AC_FILTER_MODE` | 188 | `"adaptive"` | least-squares canceller, not a notch |
| `AC_FILTER_HARMONICS` | 196 | `1` | fundamental only — deliberate, see §6.4 |
| `EMG_FILTER_TYPE` | 200 | `"butter"` | 4th order |
| `EMG_QRS_GATED` | 206 | `True` | inert at 150 Hz, decisive at 25 Hz |
| `EMG_GATE_NOISE_LIMIT` | 215 | `0.012` | per-lead HF-to-span ratio |
| `EMG_GATE_FALLBACK_HZ` | 232 | `100.0` | **added this session** |
| `BASELINE_METHOD` | 240 | `"spline"` | beat-anchored, NOT a linear high-pass |
| `ADC_PER_MV` | `ecg_report_android.py:59`, `twelve_lead_test.py:783` | `1184.0` | see §7.1 — disputed |

---

## 4. What was found

### 4.1 IEC 60601-2-25 — measured, with one qualifier

**All figures independently re-measured by a verification pass; the first version of
this section was wrong and is corrected here.**

Full chain, coherent detection, 400 s record, DFT 0.05 / EMG 150:

| Test | Limit | Measured | |
|---|---|---|---|
| Frequency response 0.05–150 Hz, **AC off** | +0.4 / −3.0 dB | −3.010 dB @ 0.05 Hz (the exact half-power point), −0.222 @ 0.1, flat to 0.01 dB from 0.25 to 100 Hz, −0.434 @ 140, −1.175 @ 150 | PASS |
| Same, **AC 50 on** | +0.4 / −3.0 dB | **FAILS between 48.6 and 51.3 Hz** | see below |
| Impulse response (3 mV × 100 ms), DFT 0.05 | ≤ 0.1 mV | 0.025–0.032 mV | PASS |
| Impulse response slope, DFT 0.05 | ≤ 0.30 mV/s | 0.0004 mV/s | PASS |
| Stopband 175 / 200 / 240 Hz | — | −10.82 / −39.23 / **−153** dB | |

**The AC qualifier.** `AC_FILTER_MODE = "adaptive"` least-squares-fits and subtracts a
50 Hz tone in 1 s crossfaded windows. That produces a ~1.4 Hz-wide null (−3 dB from
49.3 to 50.7 Hz, −296 dB at exactly 50.00 Hz) **flanked by +0.48 dB sidelobes at 48.7
and 51.3 Hz** which also exceed the +0.4 dB limit. Any compliance statement must name
the AC setting it was measured at. Publish the passband figures as "AC filter off".

**`_compensate_zero_phase_cutoff()` had a bug, now fixed.** It applied the Butterworth
`|H|²=½` correction to the *digital* frequency, but `butter()` designs through the
bilinear transform, whose mapping is non-linear. The correction over-shot, and the
error grew with the cutoff:

```
label     old design   landed at    error  |  fixed design   landed at   error
 25 Hz      27.912       25.051     +0.20% |     27.856        25.000    0.00%
 75 Hz      83.735       76.336     +1.78% |     82.317        75.000    0.00%
150 Hz     167.470      159.719     +6.48% |    158.183       150.000    0.00%
```

Every low-pass label was wider than it stated — which is why 150 Hz used to measure
−1.18 dB instead of −3.01. Fixed by pre-warping through `tan`/`arctan`. Verified:
every cutoff now lands on its label to within 0.005%, and the chain reads exactly
−3.01 dB at each setting with the gate off.

**The DFT `0.5` setting fails this test and must not be described as compliant.** It
routes to the beat-anchored spline estimator, not a high-pass. On a bare pulse it does
nothing at all (0.000 mV, because it removed DC and no more). Injected into real
records, 18% of 288 trials exceeded the 0.1 mV displacement limit and 16% exceeded the
slope limit, with recovered pulse heights of 1.84–3.26 mV for a 3.00 mV input.

**The adaptive mains canceller is still materially better than the notch it replaced:**

```
                40 Hz    45 Hz    50 Hz     55 Hz    60 Hz
adaptive        -0.00    -0.00   -240.0    -0.00    +0.00
fixed notch     -1.60    -5.63   -240.0    -6.38    -2.21
```

### 4.2 DEFECT (fixed): the QRS gate abandoned the complex on noisy leads

The muscle filter smooths between beats and hands the QRS back, so the complex keeps its
amplitude. A lead too noisy to hand back raw used to fall through to the **plain
low-pass across the whole complex**.

Measured on `recordings/raw_all_leads_20260827_120820.csv` at 25 Hz:

| lead | noise ratio | gate | J-point shift | QRS retained |
|---|---|---|---|---|
| I, II, III, aVR, aVL, aVF | 0.006–0.008 | held | **0.000 mm** | 100.0% |
| V1 | 0.106 | fell back | −0.541 mm | 70.6% |
| V2 | 0.060 | fell back | −0.980 mm | 77.0% |
| V3 | 0.038 | fell back | **−1.115 mm** | 79.8% |
| V4–V6 | 0.033–0.041 | fell back | −0.59 … −0.92 mm | 80–82% |

The millimetres understate it. **The gate is decided per lead**, and the chest leads are
noisy far more often than the limb leads — so the artifact is not spread evenly. A
J-point depression on V1–V6 with I–aVF at exactly zero has the shape of a regional
finding and reads as anterior ischaemia.

**Fix:** `EMG_GATE_FALLBACK_HZ = 100.0`. The QRS is protected either way; the noise now
decides *what* it is protected with — the untouched trace on a clean lead, a 100 Hz
version on a noisy one. Never narrower than the operator's own setting.

| | before | after |
|---|---|---|
| J-point shift, V3 @ 25 Hz | −1.115 mm | **+0.147 mm** |
| QRS retained, V1 @ 25 Hz | 70.6% | **92.3%** |
| QRS retained, V3 @ 25 Hz | 79.8% | **98.1%** |
| limb leads | 0.000 mm / 100% | unchanged |

### 4.3 DEFECT (fixed): the gate mask covered the T wave

`detect_qrs_regions()` thresholded at the **75th percentile** of |signal| — a quarter of
all samples clear that — with a 300 ms minimum peak gap. At 59 bpm the T wave sits at
that gap and clears that threshold, so it registered as a second R peak.

On `reports/ECG_Report_12_1_DM ECG V1.0 A300_20260829_161810.json`:

| leads | peaks found | real beats | mask duty | a QRS-only mask |
|---|---|---|---|---|
| I, II, aVR, V1, V4, V5, V6 … | **20** | 10 | **32.4%** | ~12% |
| III, aVL, V2, V3 | 10 | 10 | 16.2% | ~12% |

The muscle filter then handed the **T wave** back unfiltered, mains ripple and all — on a
recording whose leads are otherwise clean. This is what made a 25 Hz print look fuzzy
beside a commercial cart's, and it is why turning the AC filter on barely helped: the
restored ripple sat *inside* the gated region, downstream of the notch.

**Fix:** the module's own R-peak criterion (99th percentile halved, 250 ms gap) and a
±60 ms window instead of ±80 ms.

| | before | after |
|---|---|---|
| gated regions per beat | 1.7 | **1.0** |
| mask duty at 59 bpm | 24–32% | **11–12%** |
| T wave inside the mask | 6 of 9 beats | **0 of 9** |
| fuzz outside the QRS (>30 Hz, 480 leads) | 9.44 µV rms | **2.26 µV** (−76%) |

`detect_qrs_regions()` is shared by three callers — the muscle gate, the adaptive mains
canceller's QRS blanking, and `sharpen_qrs_gated()`. A tighter, more correct mask helps
all three, but it **is** a shared change.

### 4.4 The OLD filter manufactures a J point at 25 Hz

This is the defect in `origin/main` and `daweical` (same file). It has **no QRS gating
and no cutoff compensation**, so its "25 Hz" lands at a real −3 dB corner of **22.4 Hz**
and runs straight across the complex.

On the 1066 leads (of 1392) where the J point is measurable in the raw trace:

| | median shift | p95 \|shift\| | leads > 0.5 mm | one-directional |
|---|---|---|---|---|
| **old filter, 25 Hz** | **−0.594 mm** | **2.406 mm** | **669 / 1066** | 80% same way |
| current build, 25 Hz | +0.015 mm | 0.157 mm | **0 / 1066** | 34% |

It is manufactured, not noise — noise scatters both ways, and the effect **scales with
the S wave**:

```
S wave 0-2 mm deep  (n=307)  ->  J shift -0.284 mm
S wave 2-5 mm deep  (n=424)  ->  J shift -0.876 mm
S wave 5-9 mm deep  (n=168)  ->  J shift -1.523 mm
```

What it does to the whole complex (lead V2, averaged):

| | raw | old filter 25 Hz | current 25 Hz |
|---|---|---|---|
| before the QRS (flat) | 0.0 mm | **−0.9 mm** (invented) | 0.0 mm |
| R peak | +7.9 mm | **+5.4 mm** (−32%) | +7.9 mm |
| S nadir | −16.2 mm | **−17.5 mm** (rings past it) | −16.3 mm |

Classic Gibbs ringing: a 22.4 Hz filter has a ~45 ms impulse response against a ~10 ms
QRS transient, so the energy spreads into the PQ segment and the J point.

**It is cutoff-dependent, not a property of the filter design:**

```
 25 Hz   median -0.201   p95 2.096   108/269 leads over 0.5 mm
 35 Hz   median -0.067   p95 1.067    46/269
 40 Hz   median -0.017   p95 0.788    29/269
150 Hz   median -0.116   p95 0.579    22/269
```

Above ~40 Hz the old filter behaves. It is specifically the low cutoffs where it stops
smoothing and starts inventing.

### 4.5 The V1 notch — a cross-over that settles it

A V1 morphology difference between two reports **of the same subject** was blamed on the
patient. It is the code. The 2×2, read by **rows**:

```
                              daweical recording    our recording
raw, no filter at all                   1.95 mm           1.49 mm
through the OLD 25 Hz                   0.00 mm           0.00 mm
through the CURRENT 25 Hz               1.55 mm           1.50 mm
```

The notch is in **both** raw recordings — daweical's is the bigger one. The old filter
erases it on both; ours keeps it on both.

The notch is real morphology, not noise: on our recording it repeats on **10 of 10 beats**
with a beat-to-beat SD of **0.20 mm** against a **1.49 mm** feature (7:1), it is absent in
V2 and V3, and it survives at 150 Hz as well as 25 Hz. All twelve leads are sampled
together, so a transport or ADC glitch would appear on all of them.

The V1 T wave is **inverted in both** recordings (−1.14 mm and −1.22 mm), and R
amplitudes match to 0.91–0.99 across nine leads — so it is not calibration either.

---

## 5. What changed in this session

All uncommitted at time of writing unless noted.

| Change | File |
|---|---|
| `EMG_GATE_FALLBACK_HZ = 100.0` — the gate no longer abandons a noisy complex | `ecg_filters.py` |
| `detect_qrs_regions()` retuned — R-peak-only threshold, ±60 ms window | `ecg_filters.py` |
| **`_compensate_zero_phase_cutoff()` pre-warping fix** — every cutoff now lands on its label | `ecg_filters.py` |
| `lead_noise_ratio()` exposed so the report and the gate share one measurement | `ecg_filters.py` |
| `frozen["lead_noise"]` populated, so `artifact_statement()` finally prints | `ecg_report_android.py` |
| **Sokolow-Lyon was a subtraction** — `rv5 - abs(sv1)` → `rv5 + abs(sv1)`, both header renderers | `ecg_report_android.py` |
| Same sign fix in the four latent generators | `ecg_report_generator.py:111`, `hrv:3701`, `hyperkalemia:4041`, `6_2:3646` |
| `_fmt_mv()` — a failed measurement prints `--`, and the index is withheld rather than summed from a zero | `ecg_report_android.py` |
| **`NON-DIAGNOSTIC` marker** on the header whenever LP < 150 Hz | `ecg_report_android.py` |
| Payload stops inventing `"0.5-150 Hz"`; emits `"unknown"` | `ecg_payload_builder.py` |
| Default `filter_emg` 25 → **150**, `filter_dft` off → **0.05** | `settings_manager.py` |
| **26 scattered fallback defaults aligned** across 6 files — they disagreed with each other | `dashboard.py`, `6_2`, `ecg_report_generator.py`, `expanded_lead_view.py`, `twelve_lead_test.py`, `ecg_payload_builder.py` |
| **One-time settings migration** (`SETTINGS_VERSION = 1`) so existing units move off a monitoring bandwidth instead of silently keeping it | `settings_manager.py` |
| Seed config updated so fresh frozen installs get 150 / 0.05 / AC 50 | `src/ecg_settings.json` |
| Regression suite, 12 tests | `tests/test_filters_jpoint.py` (new) |
| Divisor change prepared, **NOT applied** — needs clinical sign-off | `docs/pending/rv5-sv1-scale.patch` |

### 5.1 The Sokolow-Lyon defect, in full

The PDF renderer computed `rv5 - abs(sv1)`. Sokolow-Lyon is RV5 **+** |SV1|. The PDF and
the JSON payload therefore disagreed on every report:

```
report                    PDF printed    JSON said    correct
A300_20260829_161810        0.445 mV      1.813 mV    1.813 mV
A999_20260829_183033        0.206 mV      1.187 mV    1.187 mV
A989_20260829_113945        0.448 mV      2.054 mV    2.054 mV
```

The PDF is the copy a clinician reads, and it understated the index roughly fourfold
against a 35 mm threshold. Both are now 1.813 / 1.187 / 2.054.

`artifact_statement()` had **always** been able to name the leads carrying enough
interference to affect interpretation, but nothing ever populated `frozen["lead_noise"]`,
so it returned `""` on every report ever generated. It now prints:

```
2. Artifact in lead(s) V4,V5 ···················· high-frequency content
   - interpret this tracing with care
```

## 6. Decisions made

### 6.1 Ship `0.05 Hz / 150 Hz / AC 50 Hz`

**These figures were corrected by the verification pass; the originals were too
flattering.** The conclusion survives; the supporting numbers did not.

1. It is the IEC 60601-2-25 and AHA/ACCF/HRS 2007 adult diagnostic bandwidth. 25/35/40 Hz
   are monitoring settings.
2. Across the 116 reports, excluding leads whose raw beat-to-beat SD exceeds 0.5 mm
   (244 of 1389 at the J point, 198 of 1389 at ST+60), worst-case shift:

   | setting | worst J shift | worst ST+60 shift | leads over 0.5 mm |
   |---|---|---|---|
   | 150 Hz | **0.397 mm** | small | **none** |
   | 25 Hz | 0.769 mm | **1.994 mm** | 4–15 leads |

   The earlier claim of 0.044 / 0.140 mm was roughly 9× and 5× too optimistic, and
   "no setting exceeds 0.5 mm" was false — 25/35/40/75/100 each exceed it on some leads.
   **Per-lead medians are negligible at every setting (0.002–0.012 mm): the case for
   150 Hz rests on the tail, not the median.** What holds at every threshold and every
   percentile is the ordering — 150 Hz shifts the J point and ST+60 about 2–6× less than
   25 Hz, and is the only setting with no lead over 0.5 mm.
3. At 150 Hz the QRS gate is effectively inert — **0.11 percentage points** of QRS
   retention (not 0.04), with >30 Hz residual unchanged inside (45.94 vs 45.92 µV) and
   outside (5.43 vs 5.43) the complex.

   **But understand why.** The gate is inert at 150 Hz because a 150 Hz low-pass barely
   filters 500 Hz data at all — out-of-QRS residual is 5.43 µV at 150 Hz against 1.07 µV
   at 25 Hz. Nothing is handed back unfiltered because almost nothing is being removed.
   That is not the same as a protection mechanism working.

   At 25 Hz the gate is decisive: retention 100.0% on vs 83.0% off, inside-QRS >30 Hz
   residual 43.56 vs 11.90 µV, with the out-of-QRS trace untouched (1.07 vs 1.04) —
   confirming the gate stays confined to the complex.

### 6.2 Keep the gate on

At 150 Hz it costs nothing. At the operator-selected 25/35/40 it is the difference
between **97.3%** and **80.3%** QRS retention.

### 6.3 Keep 25 / 35 / 40 Hz available, but label them

They are legitimate for a restless patient or a rhythm strip. The report should print a
`NON-DIAGNOSTIC — MONITORING BANDWIDTH` marker whenever LP < 150 Hz. **Not yet
implemented** — see §7.5.

### 6.4 Do NOT raise `AC_FILTER_HARMONICS`

Measured. Once the gate mask is correct the 25 Hz low-pass already removes 150 Hz
everywhere outside the QRS; adding the 3rd-harmonic canceller moved median fuzz by
0.04 µV while costing sharp-edge fidelity. Left at 1.

### 6.5 "Smooth" is not the target

The BPL cart's `0~25Hz` print and the old build's are smoother because they discard real
content — the old filter's ungated 25 Hz costs 14.1% of QRS peak-to-peak. Do not treat
either as a quality benchmark. Compare devices at 150 Hz.

---

## 7. Open — not fixed

These matter **more** than the filter choice. A filter changes morphology; these change
every number a cardiologist reads.

### 7.1 The mV calibration is unresolved (highest priority)

Commit `2306635` ("scale: 1184 ADC per mV, measured against the Fluke's own references")
is explicit that the two anchors disagree:

- Three Fluke captures at 1.00 mV put lead II's R at 1183 / 1177 / 1191 ADC (0.5% spread)
  → **1184**, and lead II then prints 10.0 small boxes, matching the reference cart.
- But **V2 prints 14.4 boxes against 11 on that cart** — roughly **31%**.

One scalar cannot satisfy both. History: `1280` (inherited, never measured) → `1531`
(commit `95abd7e`, square wave at an unconfirmed amplitude) → `1184` (commit `2306635`).
This is a bench-calibration question, not a filter question, and it is **open**.

### 7.2 RV5 / SV1 are on a different scale from the waveform

- Waveform drawn at **1184** ADC/mV
- `RV5 = r_amp_adc / 2048.0` — `src/ecg/twelve_lead_test.py:4016`
- `SV1 = s_amp_adc / 1441.0` — `src/ecg/twelve_lead_test.py:4065`

So RV5 prints at 57.8% and SV1 at 82.2% of the drawn height. Verified across 6 reports:
**the printed RV5+SV1 is 1.45–1.56× smaller than the trace on the same page.** A
clinician measuring Sokolow-Lyon with calipers gets a different answer from the number
printed beside it. Commit `95abd7e` already flagged this and deferred it.

### 7.3 SV1 returns 0.000 on failure and is still summed

On `daweical .../A989_20260829_110042.json` the report printed `SV1 0.000 mV`,
`RV5+SV1 1.999 mV` (20.0 mm). V1's S wave is present and consistent on **11 of 11 beats**
at a median of **−1.185 mV**. True Sokolow-Lyon = 1.851 + 1.185 = **3.036 mV = 30.4 mm**.

**Understated by 10.4 mm against a 35 mm LVH threshold.** A failed measurement returned
`0` instead of "not measured", and the sum was computed from it and printed as valid.

Also: `rv5_sv1_sum = (rv5_mv - abs(sv1_mv))` — a **subtraction** — exists in
`ecg_report_generator.py:111`, `hrv_ecg_report_generator.py:3701`,
`hyperkalemia_ecg_report_generator.py:4041`, `6_2_ecg_report_generator.py:3646`.
Sokolow-Lyon is RV5 **+** |SV1|. The live 12-lead path uses the correct addition, so
current 12-lead reports are not affected; the other four paths are latent.

### 7.4 The settings file the app reads is not the one you think

`data_file()` in `src/utils/app_paths.py:41-52` returns
`Path(__file__).resolve().parents[2] / filename` in dev — the **repo root**.

```
./ecg_settings.json       filter_emg "off",  filter_ac "off",  wave_gain "5"    <-- READ
./src/ecg_settings.json   filter_emg "25",   filter_ac "50",   wave_gain "10"   <-- IGNORED
```

Everything captured recently was therefore **unfiltered at 5 mm/mV**. Resolve this before
trusting any statement about what bandwidth a given capture used.

### 7.5 The JSON claims a filter band that was never applied

`_settings_details()` in `src/utils/ecg_payload_builder.py:318-326` returns a hardcoded
block — `filter_band "0.5-150 Hz"`, `ac_filter "50 Hz"` — whenever `settings_manager is
None`. Confirmed on two recordings:

| report | PDF header | JSON |
|---|---|---|
| `A999_20260829_183033` | `Filter: Off  AC:Off` | `"0.5-150 Hz"` / `"50 Hz"` |
| daweical `A989_20260829_110042` | `LP:25Hz  AC:50Hz` | `"0.5-150 Hz"` / `"50 Hz"` |

Same recording, two documents, disagreeing about how it was filtered. Present in
daweical too, so it predates this branch.

### 7.6 Still not implemented

- **`classify()` and `axis` are computed but never drawn.** `interpretation.py` returns
  `NORMAL / BORDERLINE / ABNORMAL / UNINTERPRETABLE ECG` under `severity` and P/QRS/T
  under `axis`; no renderer reads either. `grep severity src/ecg/ecg_report_android.py`
  returns nothing. The module docstring shows `- ABNORMAL ECG -` as part of the intended
  layout.
- **A two-tier artifact threshold.** The single 0.012 limit flags leads at 0.02 where the
  J point is still readable (SD 0.30 mm). Measured tiers: above ~0.06 the lead is
  genuinely not measurable (median raw J SD 1.70 mm); above 0.12 it is 2.85 mm.
- **`tests/test_report_conclusions.py` has 4 pre-existing failures.** It still asserts the
  permitted conclusion set is exactly five labels and that `Bradycardia (non-sinus)` /
  `Tachycardia (non-sinus)` are removed. Both changed when the three QRS-duration labels
  were added and the non-sinus forms were folded into the sinus ones. **The source is
  correct; the test file is stale.**

### 7.7 Done since this file was first written

`NON-DIAGNOSTIC` marker, the Sokolow sign, the SV1-zero sentinel, the payload band, the
default cutoffs, the scattered fallbacks, the settings migration and the cutoff
pre-warping are all **implemented** — see §5. The divisor change is prepared but held:
`docs/pending/rv5-sv1-scale.patch`.

## 8. How to reproduce any of this

All harnesses were written into a scratch directory, not the repo. The recipes:

**Loading two filter modules side by side** — the only way to A/B two codebases:

```python
import importlib.util, sys
sys.path.insert(0, '/Users/deckmount/new/qww_new/src')
spec = importlib.util.spec_from_file_location('old_filters', '<other-repo>/src/ecg/ecg_filters.py')
OLD = importlib.util.module_from_spec(spec); spec.loader.exec_module(OLD)
import ecg.ecg_filters as NEW          # they coexist under distinct names
```

**Reproducing the pre-fix gate** without touching the file — monkeypatch, never edit:

```python
import ecg.ecg_filters as F
F.EMG_QRS_GATED = False               # reproduces the old fallback path
```

**Frequency response** — use **coherent detection**, not peak-to-peak, and ≥ 20 cycles at
the lowest frequency, or every low-frequency point is noise:

```python
c = 2.0/n * abs(np.sum(y[mid] * np.exp(-2j*np.pi*f*t[mid])))
db = 20*np.log10(c)
```

**Raw ADC** is in every report JSON at `ecg_data.leads_data` — 12 leads × 5000 samples at
500 Hz — and in `recordings/*.csv`. Plot scale 1184 ADC/mV; 10 mm/mV means 1 mm = 0.1 mV.

**Regenerating a report from a JSON** without touching the user's settings:

```python
from utils.settings_manager import SettingsManager
_orig = SettingsManager.get_setting; OV = {}
SettingsManager.get_setting = lambda self, k, d=None: OV.get(k, _orig(self, k, d))
OV.update({'filter_emg':'150','filter_ac':'50','filter_dft':'0.05','wave_gain':'10'})
import ecg.ecg_report_android as AR
AR.generate_report(snap_raw=[...12 arrays...], frozen={...}, patient={...},
                   filename=out, fmt='12_1', conc_list=[...], fs=500.0)
```

580 PDFs were regenerated this way (116 reports × raw/25/35/40/150) into
`reports/regen/<setting>/`, 0 failures.

---

## 9. Traps — what a future session will get wrong

**9.1 Measuring an unmeasurable quantity.** Before attributing a change in any quantity
to a filter, confirm it is measurable in the *unfiltered* trace. On a noisy lead the J
point swings several mm beat to beat, and the difference of two medians is then dominated
by the noise the filter removed. Counting *all* leads puts the worst 25 Hz J shift at
2.59 mm and flags 10 of 116 reports; counting only the **1066 of 1392** leads whose raw
beat-to-beat SD is ≤ 0.5 mm puts it at **0.324 mm and 0 reports**. The first version of
this finding was wrong for exactly this reason.

**9.2 Blaming the patient.** When two reports are stated to be of the same subject, treat
the subject as a fixed control and run the cross-over in §4.5 before reaching for
physiology or electrode placement. An electrode-height hypothesis was raised and had to
be retracted.

**9.3 Editing the wrong renderer.** `ecg_report_generator.py` is 4756 lines and looks
authoritative. It does not draw the 12-lead PDF. `ecg_report_android.py` does.
`6_2_ecg_report_generator.py` (4157 lines) has zero callers.

**9.4 Assuming the repo is the repo.** Three codebases, §2. A report found on disk may
have come from any of them; check `source_report_file` in its JSON.

**9.5 Working tree ≠ HEAD.** All the filter fixes are uncommitted. A fresh clone will
reproduce the *old* behaviour.

**9.6 The settings file.** §7.4. Do not trust `src/ecg_settings.json`.

**9.7 Steady-state numbers do not describe a 10 s strip.** Every frequency-response
figure here comes from a 400 s record. The app filters 10 s strips, where `filtfilt`'s
default padding is far shorter than the 0.05 Hz high-pass settling time — a 0.25 Hz
input comes out **35% larger** peak-to-peak than it went in (2.70 vs 2.00 mV), and
0.5 Hz 26% larger. None of the sub-1 Hz figures apply to a report strip.

**9.8 The chain is not LTI, so one sine sweep characterises one operating point.** The
QRS gate hands ±60 ms around each R peak back unfiltered when `lead_noise_ratio ≤ 0.012`,
which happened on **345 of 720 real leads (48%)**. Over those windows the roll-off does
not apply at all. The adaptive AC canceller likewise excludes detected QRS samples from
its fit. A pure sine also trips the R detector, so gated measurements on synthetic tones
are meaningless — measure with `EMG_QRS_GATED = False` to get the filter's true response.

**9.9 Sine sweeps and the `0.5` DFT setting.** `filter_dft = "0.5"` dispatches to the
beat-anchored spline baseline estimator, which is signal-adaptive — a sine sweep does not
characterise it and returns non-monotonic nonsense (−0.08 dB @ 0.5 Hz, −0.04 @ 0.3, but
−27.6 @ 0.2 and −2.31 @ 1.0). It is a good baseline remover; it is not a 0.5 Hz
high-pass and must not be described as one.

---

## 10. Hard limits — what the device cannot claim

- **500 Hz sampling caps pacing-spike fidelity.** Even at 150 Hz only ~67% of a 2 mV ×
  2 ms pacing spike survives; below 150 Hz it is ~45%. That is a sampling limit, not a
  filter limit. AHA recommends ≥ 1000 Hz where pacemaker detection matters. Do not claim
  pacing detection at 500 Hz.
- **Pediatric 250 Hz bandwidth is not achievable** at 500 Hz sampling (Nyquist 250 Hz).
- **The conclusion box is restricted by design** to eight value-derived findings and
  cannot name Asystole, VF, VT, AF, flutter, AV block, BBB or PVC/PAC even when detected.
  See `REPORT_ALLOWED_CONCLUSIONS` in `ecg_report_generator.py:1689` and §5 of the README.
- **Filtering does not fix a bad electrode.** Captures measuring 0.06–0.19 noise ratio
  need skin prep and cable routing. Of the 116 recent reports, 44 had every lead clean
  and 72 had at least one lead over the 0.012 limit — most often V1 and V4 (61 each).
