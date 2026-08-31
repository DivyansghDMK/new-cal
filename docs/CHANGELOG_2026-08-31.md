# 31 August 2026 — bench day, and what it changed

Bench session on a Fluke ProSim 8 with unit `DM ECG V1.0 A989`, then three
software changes that follow from it.

**Three commits change what a patient's report prints.** The rest are bench
results, tooling, and documentation.

---

## Changes a patient would see

### `19eddef` — one measured calibration constant, 1423 counts/mV ⚠️ largest

Four constants were shipping at once across eight files. A 1.0 mV square wave from
the ProSim, captured as raw counts off the wire, settles it:

```
lead    II    V1    V2    V3    V4    V5    V6        mean 1423, spread 0.5%
counts 1420  1424  1422  1427  1424  1422  1422
```

| was | used by | error |
|---|---|---|
| 1441 | SV1 | −1.3% — was effectively right |
| 1184 | waveform drawing, per-lead ST | read **20% high** |
| 1200 | QRS slope threshold, ST deviation | read **19% high** |
| 2048 | RV5 | read **31% low** |

**Every waveform on every report is now 17% shorter**, and every ST value with it.
RV5 rises 44%. On the 12:01 recording, lead II's R wave went from 17.6 mm to
14.6 mm at 10 mm/mV.

QRS timing was re-validated on LUDB afterwards because `adc_per_mv` feeds the QRS
border slope threshold — median 93 ms, bias +1 ms, unchanged.

```bash
git revert 19eddef      # returns to 1184/1200/2048/1441 in eight files
```

The constant now lives in [`src/ecg/calibration.py`](../src/ecg/calibration.py)
with its provenance, so it cannot drift into four values again.

### `6e63e7a` — the QRS gate is diagnostic-only

The operator selected 25 Hz and nothing changed. The gate hands the QRS back
unfiltered, and ~97% of an ECG's 25–50 Hz energy is inside the QRS, so at a
monitoring cutoff the protection removed everything the setting was asked to
remove — measured 0.994 of unfiltered where a plain 25 Hz filter gives 0.26.

`EMG_GATE_MIN_CUTOFF_HZ = 100.0`. At 150 Hz the gate still applies. At 25/35/40
it does not.

| | measured cost on a real 12-lead |
|---|---|
| worst J shift | **0.17 mm** (ST elevation is called at 1.0–2.5 mm) |
| QRS amplitude kept | **70–98%** |

```bash
git revert 6e63e7a
# or set EMG_GATE_MIN_CUTOFF_HZ = 0.0 to gate at every cutoff again
```

### `1c221f3` — no amplitude from a saturated lead

`RV5`/`SV1` return `None` when the lead touches within 4 counts of an ADC rail,
and the report prints `--`. On the 12:01 recording **six of eight channels
touched a rail**, including both V5 and V1.

A clipped peak reads *lower* than the true one, so this was not an underestimate
of a large R wave — it was a plausible-looking number with no relationship to the
patient.

```bash
git revert 1c221f3      # restores reporting an amplitude from a railed lead
```

---

## Bench results — measurement, no behaviour change

`1ea0119` `b5fd7c2` `ad7f57b` `2096521` `8e1c6e9` — all in
[`docs/BENCH_RESULTS_2026-08-31.md`](BENCH_RESULTS_2026-08-31.md).

| | measured | IEC | |
|---|---|---|---|
| 0.05 Hz | −9.0 dB hardware, **−14.7 dB with software** | −3.0 dB | ❌ |
| 0.5 / 40 / 100 Hz | −0.03 / +0.03 / −1.73 dB | | ✅ |
| 150 Hz | −6.0 dB hardware, **−8.6 dB with software** | −3.0 dB | ❌ |

```
measured -3 dB passband     0.10 Hz — 116 Hz
printed on every report     0.05 Hz — 150 Hz
```

Also settled without further hardware questions: the sampling clock is correct
(499.5 pkt/s, no loss over 8018 packets); the AD8232's 0.5–40 Hz monitoring
circuit is **not** what the board is built to (40 Hz measures +0.03 dB); and the
per-lead connected bit detects a *detached* electrode only — it read `on` while
four channels sat railed.

**Dynamic range is the finding with the largest consequence.** ±2048 counts at
1423 counts/mV is ±1.44 mV against the ±5 mV IEC asks for. Two channels cannot
sum past 2.88 mV, so Sokolow-Lyon's 3.5 mV LVH threshold is unreachable. The LVH
validation work was stopped on that basis, and a test fails if the ceiling ever
moves.

## Tooling

`2191e5a` `8c95195` — [`tools/bench_capture.py`](../tools/bench_capture.py) reads
raw ADC counts off the wire, so nothing in the software scaling chain is in the
path. It speaks the device's 22-byte binary command protocol; an earlier version
sent `1\r\n`, copied from dead code in `SerialECGReader.start()`, which is
indistinguishable from a dead link and cost most of a bench session.

## Documentation

`8e4eaeb` — how Philips, GE, Glasgow, Mortara, Schiller, BPL and Dawei present
conclusions, researched across 29 agents with nine circulating claims corrected.
`f1b24d0` — the 30 August changelog.

---

## Reverting today

```bash
git revert --no-commit 1ea0119..1c221f3
git commit -m "revert 31 August changes"
```

Or the three behavioural ones only:

```bash
git revert 1c221f3 6e63e7a 19eddef
```

## Still open after today

- **Hardware**: high-pass stages 0.05 → 0.025 Hz each, low-pass 116 → ≥150 Hz,
  input range ±1.44 → ±5 mV. And the −3 dB budget must be agreed across hardware
  and software together, or the same cascade returns in software.
- **The printed bandwidth string** still says `0.05-150 Hz`, which no longer
  matches measurement at either end.
- **The expanded-lead panel measures its own intervals** and disagrees with the
  dashboard — it reported QRS 42 ms and PR 350 ms on a tracing the dashboard read
  at 88 and 149 ms. A third measurement path that nobody has validated.
