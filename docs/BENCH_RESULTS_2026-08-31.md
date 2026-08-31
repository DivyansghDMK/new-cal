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

### But the high-pass corner is not 0.05 Hz

At 0.05 Hz the response is **0.347, or −9.19 dB**, against an IEC floor of −3.0 dB.
All eight channels agree within 0.34–0.35, so this is the filter, not noise.

Working back to the corner:

| assumed order | implied −3 dB corner |
|---|---|
| first | ~0.135 Hz |
| second | ~0.075 Hz |

A first-order 0.135 Hz corner predicts 0.965 at 0.5 Hz where we measure 0.997, so
the real response is steeper than first-order and the corner sits nearer
**0.08–0.10 Hz**. Either way it is **well above the 0.05 Hz the standard requires
and the report prints**.

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

### What the report claims, against what was measured

The header prints `0.05-150 Hz`.

| end | status |
|---|---|
| 0.05 Hz | **measured at −9.19 dB — the claim is wrong** |
| 150 Hz | **untested** — the ProSim's highest sine is 100 Hz, where we measure −1.7 dB. Depending on filter order, 150 Hz could sit at −3 to −5 dB |

Neither end of the printed bandwidth is currently supported by measurement.

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
