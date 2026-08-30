# 30 August 2026 — what changed, and how to undo each piece

Twelve commits, `2d12005` … `efbedd8`, on branch `filter-fidelity`.
`new-cal/main` was at `db630fc` before this.

**Only three of the twelve change what a patient's report prints.** The rest are
documentation, a validation tool, or changes inside a module whose labels are not
in `REPORT_ALLOWED_CONCLUSIONS` and therefore cannot reach paper.

---

## Changes a patient would see

### `1712454` — multi-lead QRS boundary enabled by default ⚠️ largest

`GLOBAL_QRS_ENABLED` in [`src/ecg/ecg_calculations.py`](../src/ecg/ecg_calculations.py)
defaulted to the empty string, so the Glasgow/Marquette multi-lead boundary was off
behind an environment variable nothing sets. Every unit measured QRS from Lead II
alone.

| | median | vs cardiologists | median error | ≤10 ms |
|---|---|---|---|---|
| single-lead (before) | 74 ms | −18 ms | 18 ms | 27% |
| multi-lead (now) | 93 ms | +1 ms | 7 ms | 63% |

On our own 239 reports: median QRS 97 → 94 ms, **`Wide QRS` appears on 24 reports
instead of 16**, and 20 reports change their QRS label.

```bash
# undo without touching code — no rebuild needed
export ECG_GLOBAL_QRS=0
# or revert the commit
git revert 1712454
```

### `ba3a340` — ST elevation thresholds became age- and sex-specific

Was a flat 1.0 mm everywhere. Now 2.0 mm for men ≥ 40, 2.5 mm for men < 40, 1.5 mm
for women in V2–V3, 1.0 mm elsewhere, per the Fourth Universal Definition of MI.
Missing age or sex falls back to 1.0 mm, which is the conservative direction.

This makes ST elevation *harder* to trigger in V2–V3, so it can only remove
findings, never add them.

```bash
git revert ba3a340    # also removes src/ecg/metrics/av_conduction.py
```

### `2d12005` — signal chain ⚠️ wide surface

Several independent fixes in one commit. If you need to undo only part of it,
revert the file rather than the commit.

| what | file | effect |
|---|---|---|
| QRS gate falls back to 100 Hz on a noisy lead instead of standing down | `ecg_filters.py` | J point in V3 moved −1.115 → +0.147 mm; V1 QRS retention 70.6% → 92.3% |
| `detect_qrs_regions()` retuned — T waves were being taken for R peaks | `ecg_filters.py` | 76% less out-of-QRS filtering |
| Zero-phase cutoff pre-warping via `tan`/`arctan` | `ecg_filters.py` | cutoffs land where they are labelled |
| **Sokolow-Lyon sign** — the PDF computed `rv5 − abs(sv1)` | `ecg_report_android.py` | index was understated roughly 4×; the JSON was always correct |
| `NON-DIAGNOSTIC` marker when the low-pass is below 150 Hz | `ecg_report_android.py` | new text on the report |
| Default filters 25 Hz → 150 Hz, DFT off → 0.05 Hz | `settings_manager.py` | **plus a one-time migration that rewrites existing units' settings** |
| Payload `filter_band` no longer hardcoded `"0.5-150 Hz"` | `ecg_payload_builder.py` | reports the real setting |

```bash
git revert 2d12005
# the settings migration does NOT undo itself — a unit already migrated stays at
# 150 Hz. To put one back:  set filter_emg to "25" and settings_version to 0
# in the unit's ecg_settings.json
```

---

## Changes no patient would see

These alter `src/ecg/metrics/av_conduction.py`, whose five labels are **not** in
`REPORT_ALLOWED_CONCLUSIONS`. A test asserts their absence, so nothing here can
print.

| commit | what |
|---|---|
| `6db8abc` | P wave noise estimated from the TP segment instead of the search window that contains the P wave. Not-assessable fell 26/30 → 5/30 on LUDB. |
| `25b1b95` | P **onset** guarded against the search-window edge, so PR stops pinning to 360 ms. Affected 55 of 191 LUDB records and 20 of 205 of ours. |
| `a384685` | **Third-degree AV Block rule removed.** It labelled 33% of normal LUDB and 51% of normal PTB-XL records as complete heart block. |
| `710306c` | **Second-degree (Mobitz I and II) removed.** 3 right against 5 wrong on the 11 real records available; two errors were atrial fibrillation. |

To restore any of these labels, revert the commit *and* answer the evidence in
[`docs/pending/av-block-labels.md`](pending/av-block-labels.md) — the removals were
not stylistic.

---

## Documentation and tooling only

Nothing executable changes. Safe to keep even if every code change above is
reverted.

| commit | what |
|---|---|
| `46ca217` | [`tools/validate_against_reference.py`](../tools/validate_against_reference.py) + `docs/REFERENCE_VALIDATION.md` |
| `eb28741` | A comment at `build_interpretation()` recording why a STEMI still prints `NORMAL ECG`, and why the one-line fix must not ship. **The fix was written, tested, and deliberately backed out** — this commit is net-zero on behaviour. |
| `cb3d054` | ST measurement cleared; the missing criteria are contiguity and slope |
| `d83bbdf` | `docs/WHAT_WE_CAN_DETECT.md` — measured inventory of all eight printable conclusions |
| `efbedd8` | The two ST criteria measured: false flags on no-ischemia records 97/149 → 10, of which 8 are real LVH strain |

---

## Reverting everything

```bash
git revert --no-commit 2d12005..efbedd8
git commit -m "revert 30 August changes"
export ECG_GLOBAL_QRS=0        # belt and braces
```

Or return the branch to where `new-cal/main` stood before the day:

```bash
git reset --hard db630fc       # discards the work; branch it first
```

---

## Reference data these numbers came from

Not in the repository — roughly 71 MB, kept at `~/ecg-reference/`.

| | n | what |
|---|---|---|
| LUDB | 200 | P/QRS/T boundaries annotated per lead per beat by two cardiologists |
| PTB-XL | 324 | SCP-coded cardiologist report per record |

```bash
python tools/validate_against_reference.py --fetch --data ~/ecg-reference
```

`pip install wfdb` pulls numpy 2.x, which breaks matplotlib 3.7 and stops PDF
generation. `pip install "numpy<2"` restores it.

---

## Still open, and deliberately not done today

- Bench calibration — four conflicting ADC-per-mV constants ship at once. Raw
  captures point to 1184; see the hardware sheet.
- **Dynamic range** — 12-bit ADC at this gain reaches ±1.7 mV where IEC 60601-2-25
  asks for ±5 mV. One existing capture came within 73 counts of the rail.
- The rhythm gate `p_present and np.std(rr) < 0.1` — 56 of 153 sinus records come
  back "Undetermined", and 13 are called atrial fibrillation.
- `Prolonged QTc` finds 4 of 23. Recommended for removal from the allow-list.
- ST slope, which does not exist in the codebase and both missing criteria need.
