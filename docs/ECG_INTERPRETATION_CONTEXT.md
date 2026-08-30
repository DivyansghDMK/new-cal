# ECG Interpretation — Working Context

**Status:** specification agreed, implementation not started
**Last updated:** 30 August 2026
**Full specification:** https://claude.ai/code/artifact/0a311b17-726f-4077-853a-c1fd457400ee

This file is the context record for the ECG auto-interpretation work: what was
provided, what was found in the code, what was decided, and what is still open.
It exists so that anyone picking this up later — or a future session — does not
have to reconstruct the discussion from scratch. The detailed criterion-by-criterion
mapping and the conclusion-box output tables live in the linked specification;
this file is the summary and the audit trail.

---

## 1. People

| Role | Who |
|---|---|
| Clinical author / authority on thresholds and wording | Dr. Razzakur Rahman, MD (Lt Col, Retd.), Associate Professor of Physiology & Sleep Lab Manager, SAMC & PGI, Indore |
| Engineering | Deckmount Electronics |
| Product | CardioX / RhythmUltra |

Dr. Rahman is the sign-off authority. Any threshold or printed sentence in the
report is a clinical statement and needs his approval before it ships.

---

## 2. Source documents provided

Three documents govern this work. Where they disagree, the split is:
**the deck holds the clinical thresholds; the Deckmount spec holds the decision
order and the output wording.**

### 2.1 `ECG_Reference_Deck.pdf` — 26 slides
Dr. Rahman's clinical teaching deck. Three sections:

- **A — Rhythm disorders:** atrial fibrillation, atrial flutter, PSVT, sinus
  bradycardia/tachycardia, 1° / 2° (Mobitz I & II) / 3° heart block.
- **B — Wave & complex abnormalities:** tall P (P pulmonale), broad notched P
  (P mitrale), narrow QRS, wide QRS, ST elevation, ST depression, ectopic beats,
  RV strain pattern.
- **C — Diagnostic thresholds:** two summary tables of voltage and interval
  cut-offs, plus standard calibration (25 mm/s, 10 mm/mV).

Note: slides 20–21 have missing images and slide 26 has truncated text
("most rightward facing lea"). A corrected, versioned deck is needed as the
source of record — see §7.

### 2.2 `Deckmount_ECG_Interpretation_Logic.pdf` — 8 pages
Deckmount's internal engineering specification. This is the document that
defines *how the engine should behave*, not just what the findings are:

- **§2 Processing pipeline** — rhythm resolved first in its own pass, then
  morphology layered on as **modifiers**, never evaluated in isolation.
  Eight ordered stages, each producing a discrete testable output.
- **§3 Rhythm decision tree** — regular vs irregular, then PR trend to
  differentiate the heart blocks. Engineering note: PR must be trended across
  **3–4 consecutive conducted beats** before the dropped beat, or Wenckebach
  gets consistently misclassified as Mobitz II.
- **§4 Wave & segment abnormalities** — detection thresholds and working
  interpretations, including **low-amplitude/absent P wave (< 0.5 mm)** which
  is not in the clinical deck.
- **§4.1 Reciprocal changes** — five infarct territories, and the rule that
  reciprocal change is a *required correlating field* whenever ST elevation is
  flagged, not an optional extra.
- **§4.2 RV strain expanded** — acute vs chronic differentiation, and the
  high-altitude population note (see §5.4 below).
- **§5 Output synthesis** — the five-slot output template and the confidence
  flags. This is the format the report conclusion box must adopt.
- **§7 Worked scenarios** — four complete examples, conditions in / sentence out.

### 2.3 Clinical notes, 29–30 August (WhatsApp + `ff (1).pdf`)
Dr. Rahman's additions, all carried into the specification:

- **RV strain lead detail:** ST depression and T inversion in leads facing the
  right ventricle — right precordial V1–V3 ± V4, and inferior II, III, aVF,
  **often most pronounced in lead III as the most rightward-facing lead**.
- **Associated RVH features:** right axis deviation, dominant R wave in V1,
  dominant S wave in V5 or V6, right ventricular hypertrophy.
- **Right axis deviation — three-lead rule:** QRS is **positive** (dominant R)
  in II, III and aVF, and **negative** (dominant S) in lead I. RAD spans
  +90° to +150°. The `ff (1).pdf` image demonstrates exactly this.
- **Complete heart block — the three features to carry to the report, verbatim:**
  1. ECG features of complete heart block
  2. Severe bradycardia due to absence of AV conduction
  3. The ECG demonstrates complete AV dissociation, with independent atrial
     and ventricular rates

  All three belong in the conclusion box **together** — the dissociation is the
  diagnosis and the bradycardia is its mechanism, so printing the rate alone
  loses the reason for it.

---

## 3. The device — facts that constrain everything

| Property | Value | What it constrains |
|---|---|---|
| Leads | 12, simultaneous | Full deck in scope. `lead_capability_matrix.py` already disables ST / MI localisation / LVH below 12 leads. |
| Sampling rate | 500 Hz | 2 ms resolution — fine for every interval in the deck, marginal for pacing spikes. |
| Resting capture | last 10 s | ~8–16 beats. Too short for burden %, PSVT onset, or repeating block cycles. |
| Holter capture | 24–72 h | The only place PSVT onset, PVC burden and AF paroxysms can honestly be assessed. |
| Calibration in settings | 25 mm/s, **5 mm/mV** | Gain is user-set and currently **half** the deck's standard 10 mm/mV. See defect D4. |
| Patient demographics | age + sex captured | Both are on the report; `analyze_ecg` already accepts `patient_gender` — but neither is used in any decision. |

---

## 4. Where the code lives

The live analysis path, verified by reading the tree (not from documentation):

```
twelve_lead_test.py            acquisition, 500 Hz, 12 leads
  └─ clinical_measurements.py  median beat, PR/QRS/QT/ST/axis, RV5/SV1
  └─ arrhythmia_detector.py    detect_primary_rhythm + detect_arrhythmia
       └─ decision_layer.py    SQI gate, confidence, hysteresis, consistency
            └─ interpretation.py   finding + criterion + implication wording
                 └─ report generators → PDF
```

Live conclusion-box chain (this is the one that matters, see defects D1–D4):

```
twelve_lead_test.update_latest_rhythm_interpretation()   ~1 s cadence, lead II
  → keyword filter collapses result to ONE string        ← the problem
  → dashboard.update_live_conclusion() builds `findings`
  → last_conclusions.json  {findings, recommendations}
  → ecg_report_generator.get_dashboard_conclusions_from_image()
  → 12 slots in the report conclusion box, padded with "---"
```

**Dead parallel stack — do not wire it up.** `ecg_pipeline.py`, `rhythm_pro.py`,
`intervals_pro.py` and `morphology_pro.py` are imported by nothing in the live
app. They contain rules that contradict the live ones (VT at HR > 120 vs ≥ 100,
QTc prolonged at 480 vs 460) and `intervals_pro.detect_qt_interval` returns a
hard-coded 400 ms for every beat. Delete or repair before Phase 1.

---

## 5. What was found in the code

### 5.1 Defects — fix before building anything new

| # | Defect | Where |
|---|---|---|
| D1 | **Nine-keyword filter discards most findings.** If the rhythm label doesn't match one of nine hard-coded keywords (AF, flutter, VT, VF, asystole, bundle branch, pre-excitation, AV block, heart block), the whole interpretation is replaced by one rate word from `_bpm_rhythm_label`. **ST elevation, ST depression, PVC and PAC are not in that list.** | `twelve_lead_test.py` `update_latest_rhythm_interpretation`, ~L4941 |
| D2 | **No code path appends an ST finding to the conclusion box.** The dashboard's `findings` list is built only from rhythm, rate, PR, QRS width and QTc. Verified independently of D1 — two separate paths, same result. | `dashboard/dashboard.py` `update_live_conclusion` |
| D3 | **"Normal Sinus Rhythm" printed on rate alone**, with no P-wave test. Contradicts Interpretation Logic §3.1, which requires P present, 1:1, normal morphology. The report generator's fallback repeats the error for "Sinus tachycardia". | `twelve_lead_test._bpm_rhythm_label`; `ecg_report_generator._build_conservative_conclusions` L314 |
| D4 | **Acquisition line states a calibration the device isn't using.** Reads `wave_gain`/`wave_speed` from settings, then ignores both and appends the literals "25.0 mm/s" and "10.0 mm/mV" — each twice. With gain set to 5 mm/mV the report asserts double the truth. | `ecg_report_generator.py` ~L420 |
| D5 | **"Automated interpretation (conservative): Normal unless measurements suggest otherwise"** is appended unconditionally — including underneath a complete heart block. | `ecg_report_generator.py` ~L436 |
| D6 | **`BBB_MIN_QRS_MS = 110.0`** — complete bundle branch block requires ≥ 120 ms; 110–120 ms is *incomplete*. The "incomplete" band sits at 100–110 where it should be 110–120. | `arrhythmia_detector.py` L635 (and dead `morphology_pro.py`) |
| D7 | **"RV5+SV1" is computed as `rv5_mv - abs(sv1_mv)`** — a difference, not a sum. Consistent across the codebase (`clinical_validation.validate_rv5_sv1_sum` encodes the subtraction as expected, matching the Android device) but it is **not** the Sokolow-Lyon index and must not be thresholded at 3.5 mV. Add a separate correct index; don't break Android parity. | `ecg_report_generator.py` L111; `clinical_measurements.py` L600 |
| D8 | **Two ST engines, two conventions.** `interpretation.st_findings` measures at J+60 with proper territories; `detect_arrhythmia` measures at R+70 against a baseline 400 ms before R, and emits its own "ST elevation" label into the same list. | `interpretation.py`; `arrhythmia_detector.py` |
| D9 | **Critical findings are deleted, not downgraded.** In `human_safety_mode`, a candidate below its confidence floor is dropped entirely — VF < 0.98, complete AV block < 0.95. Silence reads as "nothing found". Downgrade the wording instead. | `decision_layer.py` ~L302 |
| D10 | **Hysteresis applied uniformly, including to emergencies.** 5 windows to activate is right for AF, wrong for asystole/VF/VT. Exempt the critical set from *activation* delay; keep *deactivation* delay. | `decision_layer.apply_diagnosis_hysteresis` |
| D11 | **Mobitz I fires with no dropped-beat check** — a rising PR trend alone triggers it, which is common in noisy tracings where P-onset detection drifts. | `arrhythmia_detector.detect_arrhythmia` |
| D12 | **Thresholds scattered and contradictory.** QTc "prolonged" is 460 in `interpretation.py`, 480 in `rhythm_pro.py`, 470 in `_build_conservative_conclusions`, and 440/460/500 in the twelve-lead warning injector. Needs one `clinical_thresholds.py`. | multiple |

**Worked consequence of D1 + D2:** a patient with an anterior STEMI — ST elevation
2.4 mm in V1–V4, reciprocal depression in II, III, aVF, sinus rhythm at 92 bpm —
gets a conclusion box reading **"Normal Sinus Rhythm"**. The ST analysis in
`interpretation.st_findings` runs correctly and is then thrown away before the
page is drawn.

### 5.2 What already works well — don't break these

- `interpretation.py` prints each finding **beside the criterion that fired it**,
  marks the block "Unconfirmed Diagnosis" until signed, and appends the advisory.
  This scaffolding is correct and should be extended, not replaced.
- `interpretation.st_findings` — proper territories, reciprocal-change logic,
  posterior-extension detection, aVR correctly excluded, pericarditis alternative.
- `interpretation.combined_caution` — wide-complex tachycardia already raises
  "cannot exclude VT vs SVT with aberrancy" and leads the findings list. This is
  the model for every ambiguous case.
- `detect_primary_rhythm` — requires P present, PR in range, regular R-R and
  narrow QRS *before* applying a rate label. It does not simply read the rate.
- BBB morphology detection is lead-based and real (`_detect_secondary_r`,
  `_terminal_s_present`, `_broad_monophasic_r`, `_has_septal_q`).
- `_atrial_flutter_features` — R-peak blanking, 3–15 Hz bandpass, spectral energy
  ratio in the flutter band.
- QT from tangent-method T-end detection on the median beat.
- SQI gate blocks interpretation below 0.5 and returns an audit reason.
- Conclusion box already handles limb-leads-off and all-chest-leads-off.

### 5.3 Coverage against the deck

23 criteria assessed: **3 ship correctly, 13 partial, 7 not built.**

- **Ships:** sinus brady/tachy, 1° AV block, narrow QRS.
- **Not built:** PSVT, Mobitz II, P pulmonale, RV strain, LVH voltage,
  RVH voltage, low-amplitude P wave.
- **Highest clinical risk gap: Mobitz II.** It is the block that gets a
  pacemaker, and a patient in 3:2 Mobitz II currently gets a report saying
  "sinus rhythm" with an occasional pause.

### 5.4 The high-altitude note

In a chronically hypoxic, high-altitude resident population — which is this
device's population — a **chronic RV strain pattern is a common baseline
finding, not an acute event.** With no prior tracing on file the default output
is the *chronic* wording ("chronic pattern possible, correlate clinically"),
never the acute one. Escalate to acute only when the strain pattern co-occurs
with a new rhythm change (new sinus tachycardia, new RBBB).

This requires **prior-tracing comparison for the same patient**, which CardioX
does not do today. The records exist and are synced, so it is a query, not new
signal processing.

---

## 6. Decisions made

### 6.1 Every criterion gets one of four roles
This is the mechanism that answers "what is possible and what is not", and it is
what stands between a measurement and a claim about a person.

| Role | The device may print |
|---|---|
| **Diagnose** | A named rhythm, asserted. Criterion fully contained in the tracing, measurement robust, being wrong is recoverable. |
| **Flag** | The pattern plus a hedge and the number that fired it. Diagnosis needs history, symptoms, labs or a prior ECG. |
| **Measure only** | The number, on the report, with no label. |
| **Out of scope** | Nothing. Silence is the correct output. |

### 6.2 The conclusion box adopts the five-slot template

```
[Rhythm] + [Rate qualifier] + [Conduction modifier] + [Morphology/ST-T modifier] + [Confidence flag]
```

Slot 1 exactly one (mutually exclusive, priority-resolved); slot 5 exactly one,
**always present, never omitted on any tracing**. The full condition → sentence
tables for all five slots are in Part D of the linked specification.

Confidence flags: `Confirmed` / `Suggests, physician review recommended` /
`Unconfirmed, physician review required` / `Uninterpretable`.

### 6.3 Wording rules
- **"STEMI"** may be printed only as **"…STEMI pattern, likely [culprit] territory"**
  with a mandatory review flag. The bare word without the pattern qualifier or
  without the flag is prohibited.
- **"Pulmonary embolism"** may be named only as a differential —
  **"correlate clinically for pulmonary embolism"** with a Suggests flag.
  Never asserted as a finding.
- **LVH/RVH** are reported as **"voltage criteria met"**, never as "hypertrophy".
- **Causes** (COPD, mitral stenosis, digoxin effect) may appear as *considerations*
  in an implication string, never as findings.
- **No statement implying treatment** — needs pacing, requires cardioversion,
  thrombolysis indicated. The device reports findings; the physician decides.
- All thresholds are evaluated **in millivolts internally, never in rendered
  millimetres**, and the report prints its actual gain and speed.

### 6.4 Two corrections made during the discussion
Recorded because they changed the specification:

1. I initially wrote that the device must **never** print "pulmonary embolism".
   The Deckmount spec's hedged form is defensible and has been adopted instead.
   Same for "STEMI pattern".
2. I initially wrote that age and sex were not captured, following a comment in
   `interpretation.py`. They **are** captured — the report header reads both and
   `analyze_ecg` already takes `patient_gender`. That comment is outdated, and
   the sex/age-specific ST and QTc thresholds are therefore implementable now.

---

## 7. Open — needs Dr. Rahman's decision

| Point | The ambiguity | Decision needed |
|---|---|---|
| QTc in men | Deck gives normal as < 440 ms and prolonged as > 450 ms, leaving 440–450 unclassified | One boundary, or a named borderline band |
| QRS 110–119 ms | Deck calls < 120 normal; code calls 110–119 borderline and reports it | Confirm the stricter band, or align to the deck |
| QTc formula | Device switches Bazett → Fridericia outside 60–100 bpm; deck names neither | Confirm the switching rule and the printed label |
| AF ventricular rate | Deck's 100–175/min applies to untreated AF only | Confirm rate must **not** gate the AF finding |
| "Confirmed" | The output template's confidence tier collides with the report's existing "Unconfirmed Diagnosis" signature state — one page could print both | Approve renamed tiers ("Criteria met / partially met / not met"), or rule the two never share a page |
| STEMI wording | Spec authorises "anterior STEMI pattern — Confirmed, immediate physician review required" | Confirm the exact sentence — it is the strongest claim the device makes |
| Wording of every Flag | Each Flag sentence is a clinical statement, not a UI string | Review and sign finding + criterion + implication text for all new rules |
| Deck slides 20–22, 26 | Missing images; truncated text | A corrected, versioned deck to cite as the source of record |

---

## 8. Plan

| Phase | Scope | Rough size |
|---|---|---|
| **0** | 12 defects above. The conclusion-box chain (D1–D5) outranks everything else. Plus the two-pass restructure and `clinical_thresholds.py`. | ~1 week |
| **1** | Classification rules over measurements that already exist: P pulmonale, P mitrale + Morris, Sokolow-Lyon, RVH, sex-specific QTc + >500 flag, sex/age ST thresholds, ST slope, ectopy counting + bigeminy/NSVT, precordial concordance, low-amplitude P, axis bands, the five output slots. | ~2 weeks |
| **2** | Strip-wide P-wave detector (finds non-conducted P waves in the T-P segment) — unlocks Mobitz I with dropped beat, Mobitz II, 2:1 indeterminate, complete-block dissociation. Plus AF two-vote test, flutter across 4 leads, PSVT in Holter. | ~4 weeks |
| **3** | RV strain composite + S1Q3T3, prior-tracing comparison, junctional beats, ST morphology, lead-reversal detection, paced-rhythm flag, per-lead suppression. | ~3 weeks |
| **4** | Validation — MIT-BIH Arrhythmia / MIT-BIH AF / PTB-XL / LUDB / Fluke ProSim, clinician read-off with Dr. Rahman, audit-log persistence, threshold freeze and sign-off, regulatory file. | ~4 weeks |

Nothing from Phases 1–3 reaches a patient report before Phase 4 clears it.

**Standards in scope:** IEC 60601-2-25 (diagnostic electrocardiographs),
IEC 60601-2-47 (ambulatory), ANSI/AAMI EC57 (arrhythmia algorithm reporting).
CDSCO-regulated for sale in India. The wording of the report determines the
claim, and the claim determines the regulatory burden — which is why the Flag
role in §6.1 is not timidity.

---

## 9. Hard limits — what the device can never claim

Ten items, in three kinds:

**Not in the signal at all**
- "STEMI" as a bare diagnosis (needs symptoms + troponin)
- "Pulmonary embolism" asserted from S1Q3T3 (imaging-based; normal ECG in ~25% of PE)
- "Left ventricular hypertrophy" from voltage (poor sensitivity, confounded)
- Causes — COPD, mitral stenosis, digoxin effect — as findings rather than considerations
- Anything about a disconnected lead or an artifact segment
- "New" or "unchanged" without a prior tracing on file

**Not observable in the recording length**
- Paroxysmal vs persistent vs permanent AF (that is history, not this tracing)
- PSVT's abrupt onset on a 10-second resting ECG (available in Holter)
- PVC burden as a percentage from a resting strip (report counts instead)
- Mobitz I vs II at 2:1 conduction (indeterminate for a cardiologist too)

**Not the machine's to say**
- VT vs SVT with aberrancy from a single wide-complex tachycardia — the existing
  code already gets this right by raising a caution instead of choosing
- Any statement implying treatment

**The general rule:** if a statement requires information the device did not
record, the device's job is to report what it *did* record, accurately, with the
threshold that fired it, and to name what is missing.
