# Bench results — Fluke ProSim 8, 31 August 2026

Unit `DM ECG V1.0 A989`, firmware `TTECGM00V_010101`. All measurements are RAW
ADC counts read off the wire with `tools/bench_capture.py`, so no software filter
or scaling is in the path — these describe the **hardware only**.

---

## 1. Counts per millivolt — settled

ProSim square wave, 2 Hz, 1.0 mV. The `step` column is the counts-per-mV directly.

| Lead | counts/mV |
|---|---|
| II | 1420 |
| V1 | 1424 |
| V2 | 1422 |
| V3 | 1427 |
| V4 | 1424 |
| V5 | 1422 |
| V6 | 1422 |
| **mean of the seven** | **1423** |
| I | 1000 — see below |

Seven channels within **7 counts (0.5%)**.

### What the software carries, against the measurement

| constant | used by | error |
|---|---|---|
| **1441** | SV1 | **−1.3%** — effectively correct |
| 1184 | waveform, per-lead ST | reads **20% high** |
| 1200 | QRS width, ST deviation | reads **19% high** |
| 2048 | RV5 | reads **31% low** |

**1441 is right.** The other three are wrong, and the per-channel split is wrong
too — V1 and V5 measure 1424 and 1422, so there is no gain difference to encode.

An earlier analysis of patient recordings argued for 1184 on the grounds that
only it produced physiological amplitudes. That reasoning was too strong: at
1423 a lead II R wave reads 0.83 mV, which is equally physiological. Two
candidates could not be separated from recordings alone.

### Lead I reads 0.70×, and it is the simulator

| capture | lead I | reference | ratio |
|---|---|---|---|
| square 1.0 mV | 1000 | 1423 | 0.703 |
| sine 5 Hz | 337.6 | 481.8 | 0.701 |
| sine 100 Hz | 280.4 | 415.3 | 0.675 |

Stable at 0.70 across independent captures and waveform types. That is the
ProSim's own lead I : lead II ratio for performance waveforms, not a channel
fault. Confirm against the ProSim manual and close the question.

---

## 2. Dynamic range — a real hardware limit

12-bit converter, mid-rail baseline, so about ±2048 counts of swing.

```
±2048 counts ÷ 1423 counts/mV  =  ±1.44 mV
```

**IEC 60601-2-25 asks the system to handle ±5 mV.** Sokolow-Lyon diagnoses LVH at
RV5 + SV1 ≥ 3.5 mV, and an LVH patient's RV5 alone reaches 3–4 mV.

**The hardware saturates below the amplitude the diagnosis requires.** This is
measured, not inferred: an existing capture on the software laptop reached 4022
of 4095 — 73 counts of headroom — and four channels railed during this session
when a limb electrode came loose.

This is the single most significant hardware finding of the session.

---

## 3. Frequency response — the top end is fine, the bottom end FAILS

ProSim performance sine, referenced to 5 Hz. The `freq` column of each capture
confirms the generator was actually changed; an earlier sweep was invalidated
because it was not.

| freq | I | II | V1 | V2 | V3 | V4 | V5 | V6 | mean | dB | IEC +0.4/−3.0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **0.05 Hz** | 0.350 | 0.348 | 0.348 | 0.352 | 0.340 | 0.349 | 0.352 | 0.339 | **0.347** | **−9.19** | ❌ **FAIL** |
| 0.50 Hz | 0.997 | 0.996 | 0.997 | 0.997 | 0.996 | 0.996 | 0.998 | 0.997 | 0.997 | −0.03 | ✅ |
| 40.01 Hz | 1.008 | 1.015 | 1.001 | 1.000 | 1.003 | 1.011 | 0.998 | 0.994 | 1.004 | +0.03 | ✅ |
| 100.03 Hz | 0.831 | 0.862 | 0.809 | 0.801 | 0.820 | 0.845 | 0.803 | 0.786 | 0.819 | −1.73 | ✅ |

### The AD8232 40 Hz fear is disproven

The board uses one AD8232 per channel, and the datasheet's typical application
circuit is a heart-rate monitor at roughly 0.5–40 Hz. **The board is not built to
that circuit.** At 40 Hz the response is flat — −0.05 to +0.13 dB across all eight
channels — and at 100 Hz it is −1.29 to −2.10 dB, inside the −3.0 dB limit.

### But the high-pass corner is not 0.05 Hz — and we know why

At 0.05 Hz the response is **0.347, or −9.19 dB**, against an IEC floor of −3.0 dB.
All eight channels agree within 0.339–0.352, so this is the filter, not noise.

The hardware team states the design carries a **0.05–150 Hz filter**. That is
consistent with what we measured, and the explanation is that **the stages
cascade**.

Fitting *n* first-order high-pass stages, each at 0.05 Hz:

| stages at 0.05 Hz | predicted at 0.05 Hz | at 0.5 Hz | fit error |
|---|---|---|---|
| 1 | 0.707 | 0.995 | 0.1801 |
| 2 | 0.500 | 0.990 | 0.0766 |
| **3** | **0.354** | **0.985** | **0.0070** |
| 4 | 0.250 | 0.980 | 0.0493 |
| **measured** | **0.347** | **0.997** | |

Three stages fit better than any alternative, including a single stage with a
freely fitted corner (which lands at 0.132 Hz with more than twice the error).

**Each stage meets "0.05 Hz" on its own. The system does not.** Three first-order
sections in series multiply their responses, so the chain that is 0.05 Hz
per-stage is −9 dB at 0.05 Hz overall — and **IEC 60601-2-25 specifies the system
response, not the per-stage response.** This is a design error that is invisible
without a system-level sweep: every stage passes its own review.

### The fix is a component value

For three cascaded first-order stages to reach −3 dB at 0.05 Hz, each stage must
sit at **0.025 Hz** — a factor of about two below where they are now, which means
roughly **doubling each AC-coupling capacitor** (or its series resistor).

| | now | with 0.025 Hz stages |
|---|---|---|
| 0.05 Hz | 0.354 (−9.0 dB) ❌ | 0.708 (−3.0 dB) ✅ |
| 0.10 Hz | 0.716 (−2.9 dB) | 0.910 (−0.8 dB) |
| 0.50 Hz | 0.985 (−0.1 dB) | 0.996 |

Counting the actual AC-coupled stages in the schematic would confirm the fit —
if there are exactly three, this is settled.

### Why this matters more than the top end

A high-pass corner above 0.05 Hz is the classic cause of **ST segment
distortion**, and is precisely why IEC 60601-2-25 sets the limit there. The
baseline recovers too quickly after the QRS and drags the ST segment with it —
producing artifactual **ST depression after a tall R wave** and elevation after a
deep S.

Our ST rule fires on **77% of records carrying no ischemia label**
([`pending/st-severity.md`](pending/st-severity.md)). That was attributed to the
missing contiguity and slope criteria. **This measurement says part of it may be
the analog front end**, and no software filter can undo it — the content is gone
before the ADC sees it.

### The top end fails too — the low-pass corner is 116 Hz, not 150 Hz

The ProSim does reach 150 Hz (an earlier note here saying it stopped at 100 Hz
was wrong). Measured:

| lead | I | II | V1 | V2 | V3 | V4 | V5 | V6 | mean |
|---|---|---|---|---|---|---|---|---|---|
| 150 Hz | 0.503 | 0.519 | 0.497 | 0.492 | 0.506 | 0.516 | 0.495 | 0.481 | **0.501** |

**−6.00 dB**, against the −3.0 dB limit. Fitting an *n*-th order low-pass to the
5 / 40 / 100 / 150 Hz points:

| order | corner | fit error |
|---|---|---|
| 1 | 110 Hz | 0.0680 |
| **2** | **116 Hz** | **0.0115** |
| 3 | 122 Hz | 0.0317 |
| 4 | 128 Hz | 0.0614 |

A second-order low-pass at **116 Hz** fits. For 150 Hz to sit inside −3 dB, that
corner has to move to **at least 150 Hz**.

**One caveat on raising it.** Sampling is 500 Hz, so Nyquist is 250 Hz. The
present 116 Hz second-order corner attenuates 250 Hz by about −13.5 dB; moving it
to 150 Hz reduces that to about −9.4 dB. Raising the corner buys diagnostic
bandwidth and spends anti-alias margin, so the two have to be traded deliberately
rather than one adjusted alone.

## What the report claims, against what was measured

The header prints `0.05-150 Hz`. **Neither end holds.**

| | measured | IEC | |
|---|---|---|---|
| **0.05 Hz** | **−9.0 dB** | −3.0 dB | ❌ |
| 0.50 Hz | −0.03 dB | | ✅ |
| 40 Hz | +0.03 dB | | ✅ |
| 100 Hz | −1.73 dB | | ✅ |
| **150 Hz** | **−6.00 dB** | −3.0 dB | ❌ |

```
    measured -3 dB passband      0.10 Hz  —  116 Hz
    printed on every report      0.05 Hz  —  150 Hz
```

The device is a competent 0.1–116 Hz instrument. It is not the 0.05–150 Hz
instrument its own reports claim, and until either the hardware or the printed
string changes, **every report overstates the bandwidth it was recorded at**.

### Both fixes are component values

| end | cause | fix |
|---|---|---|
| low | three cascaded 0.05 Hz first-order stages, −9 dB together | each stage to **0.025 Hz** — roughly double each AC-coupling capacitor |
| high | second-order low-pass at 116 Hz | corner to **≥150 Hz**, traded against anti-alias margin at 500 Hz sampling |

## 3b. The software filter is part of the problem, and fixing hardware alone will not do

The bench measurements above are raw ADC counts, so they describe the hardware
only. Running the same frequencies through `apply_ecg_filters_from_settings()`
at the shipped defaults (EMG 150, DFT 0.05, AC 50) and multiplying the two:

| freq | software | hardware | **total** | dB | IEC |
|---|---|---|---|---|---|
| **0.05 Hz** | 0.530 | 0.347 | **0.184** | **−14.70** | ❌ |
| 0.50 Hz | 0.998 | 0.997 | 0.995 | −0.05 | ✅ |
| 5 Hz | 1.000 | 1.000 | 1.000 | 0.00 | ✅ |
| 40 Hz | 1.025 | 1.004 | 1.029 | +0.25 | ✅ |
| 100 Hz | 1.023 | 0.819 | 0.838 | −1.54 | ✅ |
| **150 Hz** | 0.745 | 0.501 | **0.373** | **−8.56** | ❌ |

The AC notch makes no difference at any of these points — it is narrow and sits
at 50 Hz, which is not a test frequency. Selecting EMG 40 collapses 100 Hz to
−14 dB, as a monitoring setting should.

### Why the software adds so much at 0.05 Hz

`apply_dft_filter` at its "0.05" setting measures **0.713 at 0.05 Hz** — not 1.0.
Two reasons compound:

- **Zero-phase filtering squares the magnitude.** The filter runs forwards and
  backwards, so a design that is −3 dB at its corner ends up at −6 dB there.
- The rest of the chain contributes a further factor of about 0.74 (the full
  software chain measures 0.530 where the DFT stage alone is 0.713), most likely
  the baseline-wander stage.

So the complete signal path contains **four high-pass sections at a nominal
0.05 Hz** — three in hardware, one in software counted twice for filtfilt.

### The consequence: the hardware fix is not sufficient on its own

| | response at 0.05 Hz | total |
|---|---|---|
| hardware corrected to −3 dB | 0.708 | |
| software still at the 0.05 setting | × 0.713 | **0.505 = −5.94 dB** ❌ |
| software baseline filter off | × 1.000 | **0.708 = −3.00 dB** — exactly at the limit |

**−3 dB is a budget for the whole system, not a target for each stage.** Hardware
and software cannot both spend it. Once the hardware genuinely reaches 0.05 Hz,
the software baseline filter has to move well below it or come out of the path
entirely — otherwise the same cascade returns in a different place.

This is the same mistake at a different layer, and it is worth stating plainly:
**every stage in this chain was specified at 0.05 Hz, and nobody multiplied them
together.**

## 4. Answered as a side effect

**Sampling clock is correct.** The application reported `499.5 pkt/s`, `no packet
loss`, `perfect packet continuity` over 8018 packets. A clock error would scale
every printed interval; there is none. This closes the question that was queued
for the hardware team.

**Lead-off detection exists but does not detect this.** Every packet carries a
per-lead connected bit (`MSB & 0x20`). It read `on` while V6 sat pinned at
baseline 1, and again while four chest channels were railed at 0. **It detects a
detached electrode, not a saturated or mis-referenced channel** — so it cannot,
on its own, explain or triage the 72 of 116 reports carrying an over-limit lead.

**One loose limb electrode corrupts all six chest leads.** Chest leads are
measured against the Wilson Central Terminal, WCT = (RA+LA+LL)/3, so a single
limb electrode failing shifts every V lead's baseline at once. Observed directly
this session: V2–V5 all railed together while the limb leads stayed plausible.

---

## 5. What this changes in software

Nothing has been changed yet — the divisor touches every printed amplitude and
needs Dr. Rahman's sign-off. What it implies:

| | today | with 1423 |
|---|---|---|
| ST per lead | divides by 1184 → **20% high** | thresholds finally mean millimetres |
| RV5 | divides by 2048 → **31% low** | Sokolow-Lyon stops understating |
| SV1 | divides by 1441 | already correct |
| QRS slope threshold | 1200 | 19% off, affects border sensitivity only |

The 20% ST over-reading is a partial explanation for the ST rule firing on 77% of
records with no ischemia label — the −0.5 mm depression threshold was being
crossed 20% too easily. It is not the whole story; the missing contiguity and
slope criteria remain the larger part.

---

## 6. Still to do on the bench

1. **T2 amplitude sweep** — find the exact input at which each channel clips,
   rather than inferring ±1.44 mV from the divisor.
3. **T4 known ST deviation** — the ProSim can inject a known ±mV ST offset. This
   is the only way to validate the millimetres in every ST threshold, and no
   dataset can substitute for it.
4. **T6 arrhythmia library** — captures of real AV blocks, which are the ground
   truth a rebuilt second/third-degree rule would need.
