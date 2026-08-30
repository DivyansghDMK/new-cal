# 🫀 CardioX - Professional ECG & Cardiac Analysis Platform

CardioX is a clinical-grade, hardware-integrated desktop application designed for real-time ECG monitoring and advanced cardiac analysis. The platform processes, classifies, and tracks cardiac metrics with professional medical-grade precision.

---

## 🌟 Key Features

### 1. Rebranded Premium Medical Identity (CardioX)
- **Harmonious Theme:** Tailored UI utilizing orange, tech blue, and medical teal colors.
- **Custom Visual Assets:** High-resolution transparent logo (`assets/cardiox_logo.png`) and fully compliant multi-resolution Windows icon (`assets/cardiox_logo.ico`).
- **Windows Taskbar Integration:** Declares an explicit Windows `AppUserModelID` (`CardioX.1.1.0`) so the OS correctly clusters the custom CardioX taskbar icon instead of fallback Python interpreter icons.
- **Clean Dashboard Layout:** Hides the "Comprehensive ECG" button (`self.holter_btn`) to keep the dashboard focused entirely on core workflows.

### 2. Dedicated Hardware Lock (Device Authorization)
- **Secure Signup Association:** During license signup/registration, the serial number of the user's specific RhythmUltra hardware is bound and stored inside the license token (`cardiox.lic`).
- **Acquisition Lockdown:** Real-time data acquisition in the three core modules (**12-Lead ECG**, **HRV**, and **Hyperkalemia**) is restricted. The software strictly validates the connected physical USB device against the signup token serial number, preventing unauthorized hardware usage.

### 3. Professional Medical Dashboard & Diagnostics
- **High-Fidelity Trace Viewer:** Sub-pixel waveform rendering using PyQtGraph with strict grid snapping and dynamic overlay pins.
- **Beat Morphology Classification:** Real-time event tagging (N, V, S, AF) and clustering of abnormal beats (VE, SVE) for rapid medical review.
- **HRV Analytics:** Real-time calculations of Time Domain metrics (SDNN, rMSSD, pNN50) and interval stats (PR, QRS, QT, QTc).

### 4. Zero-Collision Cloud Synchronization
- **Asynchronous S3 Offloading:** Automatic background thread offloading of ECG data to AWS S3 every 15 seconds.
- **Local Cache Queueing:** Zero data loss offline-first architecture; queued files auto-sync the moment internet access is restored.

---

## 🛠️ Tech Stack
- **Core Engine:** Python 3.10
- **User Interface:** PyQt5, PyQtGraph (Hardware-accelerated rendering)
- **Signal Analysis:** NumPy, SciPy (FFT, digital filtering)
- **Report Generation:** ReportLab, Matplotlib (Agg background renderer)
- **Packaging & Setup:** PyInstaller, Inno Setup 6

---

## 🚀 Quick Start (Developers)

```powershell
# 1. Activate your virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the application
python src\main.py
```

---

## 📦 Release Compilation & Installer Packaging

CardioX uses a unified release pipeline script to compile the application and generate a single-file Windows setup installer:

```powershell
# Run the release script to compile and build the installer
.\build_release.ps1 -Name CARDIOX -Version 1.1.0
```

### Build Details:
1. **PyInstaller Compilation:** Packages python scripts into a standalone executable. Uses `--icon=assets/cardiox_logo.ico` to embed the square padded multi-resolution logo directly into the output binary (`dist\CARDIOX\CARDIOX.exe`).
2. **Inno Setup Integration:** Invokes Inno Setup compiler (`ISCC.exe`) using [CardioX.iss](file:///c:/Users/DELL/Documents/QW/qww/installer/CardioX.iss) to package the setup program, apply shortcut icon mappings (Desktop, Start Menu, Uninstaller), and create the final installer.
3. **Installer Output:** Generates the ready-to-run installation executable at `dist\installers\Setup_CARDIOX_1.1.0.exe`.

---

## 📝 Admin & Demo Configuration

**Admin Dashboard Credentials:**
- **User:** `admin` / **Password:** `adminsd`

**Demo Mode:**
A simulated hardware mode is supported. If no device is connected, static `.ecgh` datasets can be replayed to demonstrate trace rendering, clinical algorithms, and PDF report generation.

---
**Status:** 🟢 Production Ready | **Last Updated:** August 2026

---

## 🧪 Running Tests

The project includes a headless unit test suite (no display or hardware required):

```powershell
# Install pytest if not present
pip install pytest

# Run the full test suite
python -m pytest tests/ -v

# Run only the history/hyperkalemia tests
python -m pytest tests/test_history_and_hyperkalemia.py -v

# Run only the production deployment tests
python -m pytest tests/test_cardiox_prod.py -v
```

> **Current Coverage:** 324 tests across 46 test classes covering authentication, signal processing, PDF generation, offline queue, connectivity, and clinical metric classification — **100% PASSING** (76 in `test_cardiox_prod.py`, 104 in `test_history_and_hyperkalemia.py`, 144 in `test_input_validation.py`).

The unit suite runs headless and cannot exercise the packaged executable. Verification of the built
EXE — PyInstaller bundling, installer, licence heartbeats, USB acquisition, PDF output — is covered by
the acceptance checklist below.

---

## 📚 Documentation

| Document | Covers |
|---|---|
| [docs/EXE_TEST_CHECKLIST.md](docs/EXE_TEST_CHECKLIST.md) | Release verification for the built EXE and installer — 185 tick-box checks across 18 layers (build, installer, launch, licensing, device, clinical modules, reports, cloud, security, uninstall), plus regression checks for the current fix set and a sign-off sheet. |
| [docs/ReportScreen_kt.md](docs/ReportScreen_kt.md) | Full reference for the Android report screen [ReportScreen.kt](ReportScreen.kt) — coordinate system, layout geometry for 1×12 / 2×6 / 3×4, waveform maths, PDF export, threading, known issues, and a 40-check verification list. |
| [docs/comprehensive_ecg_analysis_architecture.md](docs/comprehensive_ecg_analysis_architecture.md) | Analysis pipeline architecture. |

### Excel & Word versions

The two checklists above are also published as fillable office documents for testers who work outside
a code editor:

| File | Format | Use |
|---|---|---|
| [docs/CardioX_EXE_Test_Checklist.xlsx](docs/CardioX_EXE_Test_Checklist.xlsx) | Excel | One row per check with a **PASS / FAIL / N/A / BLOCKED** dropdown that colours itself, autofilter, frozen headers, and a **Summary** sheet whose per-layer totals and release verdict recalculate live. Includes Environment, Defect Log and Sign-off sheets, plus a separate sheet for the 40 Android checks. |
| [docs/CardioX_EXE_Test_Checklist.docx](docs/CardioX_EXE_Test_Checklist.docx) | Word | Landscape print-and-tick record — one table per layer with ☐ Pass / ☐ Fail boxes, blocking layers flagged in the heading, defect log and signature block at the end. |
| [docs/CardioX_ReportScreen_Kotlin.docx](docs/CardioX_ReportScreen_Kotlin.docx) | Word | The `ReportScreen.kt` reference as a formatted document, with all tables and code blocks preserved. |

**The markdown files remain the single source of truth.** Edit those, then regenerate:

```powershell
python docs\generate_checklist_docs.py
```

The generator needs `openpyxl` and `python-docx` (`pip install openpyxl python-docx`).

---

## 🔐 Licensing & Device Authorization

The licensing rules below are the product specification. Treat them as authoritative
when changing `src/utils/license_manager.py`, the login flow in `src/main.py`, or the
`cardiox-license-*` Lambdas.

### Business rules

| # | Rule |
|---|---|
| 1 | **Signup** creates the account server-side and shows the user their credentials once. |
| 2 | **One RhythmUltra device allows 5 signups** — five *different* machines may share one device serial (e.g. `DM ECG V1.0 A010`). |
| 3 | **Revocation stops the software.** Login is blocked, the user is told the licence is revoked and to contact Deckmount support, every local credential is wiped, and they are returned to Sign Up. |
| 4 | **A revoked user may not sign up again.** The server must refuse re-registration. Otherwise revocation is meaningless — the customer is running again in under a minute. |
| 5 | **Releasing a seat is a separate admin action** that re-opens registration. Only after a seat is explicitly freed may that user register again. |
| 6 | **Offline grace is 7 days.** A periodic server heartbeat is mandatory — it is what prevents a one-time signup being used indefinitely on a machine that never contacts the server again. |
| 7 | **The final 3 days of the offline window show a warning** on every launch: internet is required for verification or the software will stop. |
| 8 | **Exhausting offline grace must never wipe credentials.** Unlike revocation, the user simply needs to get back online. Local `users.json` records are never deleted — that is shared clinical data. |

Revocation is detected **only** by the Check-5 heartbeat inside `run_startup_checks()`.
Never make that call conditional on local state such as a token file existing; doing so
silently disables revocation enforcement entirely.

### Enforced in the client

| Behaviour | Where |
|---|---|
| Revoked seat blocks login, wipes credentials, returns to Sign Up | `src/main.py` |
| Licence gate **fails closed** — an error in the gate denies access rather than falling through to login | `src/main.py` |
| Developer auto-login gated behind `CARDIOX_DEV_AUTOLOGIN` (default off) | `src/main.py`, `src/auth/sign_in.py` |
| 7-day offline grace with a 3-day countdown warning | `src/utils/license_manager.py` |
| Signup failures show a specific dialog — device limit, revoked, or server unreachable | `src/utils/license_dialog.py` |
| Server-side secrets stripped from the distributed `.env`; build aborts on an unvetted secret | `build_exe.py` |

Both revocation codes the server emits (`LICENSE_REVOKED` for a revoked licence,
`ACCOUNT_REVOKED` for a revoked seat) map to the same user-facing message, so the wording
does not depend on which one arrived.

### Enforced in the database

Applied by `license_server/migrations/001_seat_integrity.sql`:

- unique index on `(license_id, bound_fingerprint)` — one live seat per machine per licence
- unique index on `(license_id, seat_number)`
- `CHECK` constraint restricting `plan_type` to `single` / `clinic` / `hospital` / `enterprise`
- `trg_supersede_duplicate_seat` — **temporary**, substituting for the fingerprint dedup the register Lambda is missing

**Releasing a seat requires two statements.** Updating `license_seats` alone leaves the
licence at `status='active'` with no seats, and the register path only draws licences
whose status is `'unused'`, so the key is stranded permanently:

```sql
UPDATE license_seats
   SET status='revoked', revoked_at=NOW(), released_at=NOW()
 WHERE rhythmulta_serial = :serial AND status='active';

UPDATE licenses l SET status='unused'
 WHERE l.id = :license_id
   AND NOT EXISTS (SELECT 1 FROM license_seats s
                    WHERE s.license_id = l.id AND s.status='active');
```

Seat status values: `active` (live), `revoked` (admin block), `superseded` (retired by
the dedup trigger when the same machine re-registered — not a licensing decision).

### Known gaps

Not yet implemented in `cardiox-license-register`:

- **Rule 4 is not enforced** — a revoked user can still sign up again. Needs a refusal when
  a seat exists for the fingerprint with `status='revoked' AND released_at IS NULL`.
- `license_key` in the request body is ignored entirely; a key absent from the database
  returns the same response as a valid one.
- No hardware fingerprint dedup, which is why the database trigger exists.
- `seat_number` is derived as `COUNT(*)+1` rather than `MAX(seat_number)+1`, so it
  collides after any row deletion.
- Resolve → check → insert is not wrapped in a transaction, so two concurrent signups can
  both pass the seat-cap check.

Client-side, tokens are signed by the server with `JWT_SECRET` but verified against
`LICENSE_HMAC_SECRET`, so offline signature verification cannot succeed. Real offline
tamper detection requires moving to RS256 and shipping only the public key.

---

## 🩺 The Filter Chain

Reference for what each filter setting does, what it has been measured at, and the
one artifact it used to produce. The rules live in
[src/ecg/ecg_filters.py](src/ecg/ecg_filters.py); thresholds shared with the
dashboard live in [src/ecg/interpretation.py](src/ecg/interpretation.py).

### Order and settings

`apply_ecg_filters()` runs three stages, always in this order:

| Stage | Setting | Options | What it does |
|---|---|---|---|
| 1. DFT | `filter_dft` | `off` / `0.05` / `0.5` | Baseline wander. `0.05` is a 2nd-order zero-phase Butterworth high-pass; `0.5` routes to the beat-anchored spline estimator instead. |
| 2. EMG | `filter_emg` | `off` / `25` / `35` / `40` / `75` / `100` / `150` | Muscle artifact low-pass, QRS-gated. **Default `150`.** |
| 3. AC | `filter_ac` | `off` / `50` / `60` | Mains. Adaptive least-squares canceller by default, fixed IIR notch available. |

Cutoffs are pre-compensated for `filtfilt`'s double pass
(`_compensate_zero_phase_cutoff()`), so a "150 Hz" setting really is −3 dB at
150 Hz. Without it the real corner lands at ~134 Hz — inside the diagnostic band.

### Measured against IEC 60601-2-25

Full chain at 500 Hz, DFT 0.05 / EMG 150 / AC 50, coherent detection at each tone:

| Test | Limit | Measured | |
|---|---|---|---|
| Frequency response 0.05–150 Hz | +0.4 / −3.0 dB | −3.01 dB @ 0.05 Hz, −1.18 dB @ 150 Hz, −0.44 … +0.03 dB between | PASS |
| Impulse response (3 mV × 100 ms), displacement | ≤ 0.1 mV | 0.027 mV @ DFT 0.05, 0.015 mV @ 0.5 | PASS |
| Impulse response, post-pulse slope | ≤ 0.30 mV/s | 0.000 mV/s | PASS |
| Mains rejection at the selected frequency | — | −110 dB (50), −121 dB (60) | |
| Selectivity: 60 Hz tone with the 50 Hz setting | untouched | −0.00 dB | |
| Stopband 175 / 200 / 240 Hz | — | −10.8 / −39.3 / −81.0 dB | |

**Why the adaptive canceller is the default.** Measured side by side against the
fixed IIR notch it replaced:

```
              40 Hz    45 Hz    50 Hz     55 Hz    60 Hz
adaptive      -0.00    -0.00   -240.0    -0.00    +0.00
fixed notch   -1.60    -5.63   -240.0    -6.38    -2.21
```

The notch's −5.63 dB at 45 Hz and −6.38 dB at 55 Hz would on their own fail the
±3 dB IEC window, and that band carries real QRS energy. On a mains-free beat the
notch injects 3.3 µV pk of ringing against the canceller's 0.3 µV. Only the
fundamental is cancelled (`AC_FILTER_HARMONICS = 1`); the 3rd harmonic that often
dominates chest-lead pickup is left alone, because a sharp edge has genuine energy
there too.

**The `0.5` DFT setting is not a 0.5 Hz high-pass.** It is the beat-anchored spline
estimator, which is signal-adaptive, so a sine sweep does not characterise it — and
the sweep bears that out: −0.08 dB @ 0.5 Hz, −0.04 @ 0.3, but −27.6 @ 0.2 and
−2.31 @ 1.0 Hz, non-monotonic. It is a good baseline remover and it leaves genuine
ST shift intact (3 mm injected → 3.04 mm measured), but it cannot be validated by
the IEC method and should not be described as a 0.5 Hz band.

### The QRS gate, and the artifact it used to leave

The muscle filter does not run one cutoff across the whole beat. It smooths hard
between beats and hands the QRS back, so the complex keeps its amplitude and
nothing smears into the J point. A 25 Hz cutoff has a 52 ms impulse response,
which is longer than the 20 ms feature it would otherwise be filtering.

Handing the QRS back *unfiltered* only works on a clean lead — on a noisy one it
hands back the interference too, printing as a burst at every complex. So
`lead_noise_ratio()` measures each lead's high-frequency content as a fraction of
its own span, and `EMG_GATE_NOISE_LIMIT = 0.012` decides. Clean captures on this
hardware sit at 0.005–0.011; leads still carrying mains measure 0.013–0.106.

**The defect:** a lead over that limit used to fall all the way back to the plain
low-pass — the selected cutoff run straight across the QRS. Measured on
`recordings/raw_all_leads_20260827_120820.csv` at 25 Hz:

| lead | noise ratio | gate | J-point shift | QRS retained |
|---|---|---|---|---|
| I, II, III, aVR, aVL, aVF | 0.006–0.008 | held | **0.000 mm** | 100.0% |
| V1 | 0.106 | fell back | −0.541 mm | 70.6% |
| V2 | 0.060 | fell back | −0.980 mm | 77.0% |
| V3 | 0.038 | fell back | **−1.115 mm** | 79.8% |
| V4 | 0.033 | fell back | −0.921 mm | 82.3% |
| V5 | 0.035 | fell back | −0.731 mm | 81.3% |
| V6 | 0.041 | fell back | −0.594 mm | 80.5% |

The millimetres understate it. The gate is decided **per lead**, and the chest
leads are the noisy ones far more often than the limb leads are — so the artifact
is not spread evenly across the page. A J-point depression sitting on V1–V6 with
I–aVF at exactly 0.000 mm has the shape of a regional finding, and reads as
anterior ischaemia. The 20–29% voltage loss in the same leads also lands directly
on Sokolow-Lyon (SV1 + RV5), which the report prints.

No new notch is invented — the S-wave minimum is already there on 11/11 beats
either way. What moves is the *level* of the J point.

**The fix.** `EMG_GATE_FALLBACK_HZ = 100.0`. The QRS is protected either way; the
noise decides what it is protected *with* — the untouched trace on a clean lead, a
100 Hz version on a noisy one. Never narrower than the operator's own setting, so
EMG 150 does not quietly become a 100 Hz low-pass. Same recording, after:

| | before | after |
|---|---|---|
| J-point shift, V3 @ 25 Hz | −1.115 mm | **+0.147 mm** |
| QRS retained, V1 @ 25 Hz | 70.6% | **92.3%** |
| QRS retained, V3 @ 25 Hz | 79.8% | **98.1%** |
| limb leads | 0.000 mm / 100% | unchanged |

Pinned by [tests/test_filters_jpoint.py](tests/test_filters_jpoint.py), which
compares the fallback against the plain low-pass it replaced rather than against a
constant, so the test fails if the old behaviour ever returns.

### The gate mask must cover the QRS and nothing else

`detect_qrs_regions()` decides which samples get handed back less filtered than
the rest of the trace. Every caller depends on it — the muscle filter's gate, the
adaptive mains canceller's QRS blanking, and `sharpen_qrs_gated()` — so anything
wrongly inside the mask keeps its noise on the printed page.

It used to threshold at the **75th percentile of |signal|** (a quarter of all
samples clear that) with a 300 ms minimum peak gap. At 59 bpm the T wave sits
right at that gap and cleared that threshold, so it registered as a second R peak.
Measured on `ECG_Report_..._A300_20260829_161810`:

| lead | peaks found | real beats | mask duty | a QRS-only mask |
|---|---|---|---|---|
| I, II, aVR, V1, V4, V5, V6 … | **20** | 10 | **32.4%** | ~12% |
| III, aVL, V2, V3 | 10 | 10 | 16.2% | ~12% |

The muscle filter then handed the **T wave** back unfiltered, mains ripple and
all. That is what made a 25 Hz print look fuzzy beside a commercial cart's at the
same setting, on a recording whose leads are otherwise clean (noise 0.006–0.012,
50 Hz only 0.01–0.14 mm). It also explains why turning the AC filter on barely
helped: the ripple being restored sat *inside* the gated region, downstream of the
notch.

Fixed by using the same R-peak criterion the rest of the module already uses —
99th percentile halved, 250 ms gap — and a ±60 ms window instead of ±80 ms, since
a QRS is ~100 ms wide and ±80 ms reached into the ST segment:

| | before | after |
|---|---|---|
| gated regions per beat | 1.7 | **1.0** |
| mask duty at 59 bpm | 24–32% | **11–12%** |
| T wave inside the mask | 6 of 9 beats | **0 of 9** |
| visible fuzz outside the QRS (>30 Hz residual, 480 leads) | 9.44 µV rms median | **2.26 µV** (−76%) |

Raising `AC_FILTER_HARMONICS` to also cancel the 150 Hz third harmonic was
measured alongside and left out: once the gate is correct the muscle filter
already removes 150 Hz everywhere outside the QRS, so it changed the median fuzz
by 0.04 µV while costing the sharp-edge fidelity the constant's comment warns
about.

### Why the default is 150 Hz

Across the 116 reports captured on 2026-08-28/29 — 1392 leads in total.

**A shift can only be measured where there is something to shift.** 335 of those
leads (24%) have no measurable J point in the *raw* trace at all: it swings more
than 0.5 mm beat to beat before any filter touches it. Beat-to-beat scatter of the
raw J point, against the lead's own noise ratio:

| lead noise ratio | leads | median raw J scatter (SD) |
|---|---|---|
| 0.000 – 0.012 (clean) | 846 | 0.09 mm |
| 0.012 – 0.03 | 170 | 0.30 mm |
| 0.03 – 0.06 | 226 | 0.42 mm |
| 0.06 – 0.12 | 121 | **1.70 mm** |
| above 0.12 | 29 | **2.85 mm** |

On the 1057 leads where the raw J point IS measurable, filter-induced shift:

| setting | worst J | p99 J | median J | worst ST | median ST | leads with ST shift > 0.5 mm |
|---|---|---|---|---|---|---|
| 25 Hz | 0.324 mm | 0.231 | 0.007 mm | 0.140 mm | 0.015 mm | **0 / 1057** |
| 35 Hz | 0.331 mm | 0.238 | 0.002 mm | 0.129 mm | 0.006 mm | 0 / 1057 |
| 40 Hz | 0.331 mm | 0.238 | 0.001 mm | 0.136 mm | 0.005 mm | 0 / 1057 |
| 100 Hz | 0.346 mm | 0.237 | 0.000 mm | 0.245 mm | 0.002 mm | 0 / 1057 |
| **150 Hz** | 0.300 mm | 0.191 | 0.000 mm | **0.044 mm** | 0.001 mm | 0 / 1057 |

With the fallback fix in place every setting is well inside a clinically read
amount — the worst single lead at 25 Hz moves 0.32 mm and the median moves 0.007 mm.
150 Hz is still the tightest by a factor of three on ST, which is why it is the
default, but 25 Hz is no longer producing an artifact.

> **A measurement trap worth recording.** Counting *every* lead instead of only the
> measurable ones puts the worst-case J shift at 25 Hz at 2.59 mm and flags 10 of
> 116 reports as moving ST by more than 0.5 mm. Those numbers are not the filter.
> On a lead whose raw J point already swings 7.35 mm beat to beat, the difference
> between two medians is dominated by the noise the filter removed, not by anything
> the filter did to the signal. The tell is that the 25 Hz filter *reduces* the
> scatter — 2.15 mm SD raw to 0.67 mm filtered on that same lead. Always check that
> the quantity is measurable in the unfiltered trace before attributing a change in
> it to the filter.

150 Hz is also the bandwidth IEC 60601-2-25 asks for. Carts ship it as the
diagnostic default and label 25/35/40 as an explicit operator choice; so do we.
Existing installations keep whatever is in their own `ecg_settings.json` — the
change affects new installs only.

### Naming the leads that were smoothed

`artifact_statement()` has always been able to print which leads carry enough
interference to affect interpretation, but nothing ever populated
`frozen["lead_noise"]`, so it returned `""` on every report and the reader was
never told. It is now populated in
[ecg_report_android.generate_report()](src/ecg/ecg_report_android.py) from
`lead_noise_ratio()` — the same measurement the gate switches on, so the leads
named are exactly the leads that took the fallback path:

```
2. Artifact in lead(s) V4,V5 ······················· high-frequency content
   - interpret this tracing with care
```

Of the 116 recent reports, 44 had every lead clean and 72 had at least one lead
over the limit — most often V1 and V4 (61 reports each).

---

## 🧾 The PROBABLE CONCLUSION Box

Reference for what is printed inside the conclusion box on the 12-lead report, and
for the rules that decide it. This section describes the **current** behaviour; the
changelog entry below it records the state at the time the allow-list was introduced.

### Which generator actually draws it

There are several report generators in the tree and only one of them reaches paper
for the 12-lead PDF:

| File | Status |
|---|---|
| [src/ecg/ecg_report_android.py](src/ecg/ecg_report_android.py) | **Live.** `generate_report()` is what [twelve_lead_test.py:8524](src/ecg/twelve_lead_test.py) and [analysis_window.py:3202](src/dashboard/analysis_window.py) call. `_draw_footer_portrait()` / `_draw_footer_landscape()` draw the box. |
| [src/ecg/interpretation.py](src/ecg/interpretation.py) | **Live.** `build_interpretation()` supplies the box contents. Free of Qt, matplotlib and file I/O so the rules can be tested directly. |
| [src/ecg/ecg_report_generator.py](src/ecg/ecg_report_generator.py) | Owns the allow-list helpers that the live path imports, but its own ReportLab drawing code (`conclusion_header` at line 4237) is **not** the box on the PDF. |
| `hrv_ecg_report_generator.py`, `hyperkalemia_ecg_report_generator.py`, `6_2_ecg_report_generator.py` | Separate modules, separate boxes. |

This distinction is not cosmetic: the allow-list was originally applied only to
`ecg_report_generator.generate_ecg_report()`, which the 12-lead page never calls, so
`Asystole` kept printing after the restriction was supposedly in place. It is pinned
by `TestAndroidReportPathIsFiltered` in `tests/test_report_conclusions.py`.

### What appears in the box

```
PROBABLE CONCLUSION                Please consult your doctor  -  Unconfirmed Diagnosis if not signed
1. Normal Sinus Rhythm ························································· V-rate 60, 60-100
   - P wave before every QRS, 1:1 conduction, rate 60-100
2. Wide QRS ···················································································· QRSD 132, >= 120mS
   - bundle branch block, ventricular rhythm, hyperkalaemia, Na-channel blockade or paced rhythm
```

**Header row.** `PROBABLE CONCLUSION` bold left; right-aligned italic carries
`advisory` + `caveat`. The advisory (*"Please consult your doctor"*) always prints —
the box holds an algorithm's reading, not a clinical opinion. The caveat
(*"Unconfirmed Diagnosis if not signed"*) drops once `frozen["signed"]` is true.

**Up to 5 numbered statement rows**, each a `(finding, criterion, implication)` triple:

| Part | Size | Position | Source |
|---|---|---|---|
| **Finding** | 8.5 pt | left | the permitted label |
| **Criterion** | 7.5 pt | right, dotted leader between | `criterion_for()` — the measurement and threshold that fired |
| **Implication** | 6.5 pt italic | indented on its own line | `_IMPLICATIONS` — what the finding suggests |

Printing the criterion beside the finding is what makes the output auditable: the
reader can see which measurement drove the statement and check it against the values
in the report header, rather than taking the label on trust. The implication line
saves them translating a threshold into a differential.

**Assembly order** inside `build_interpretation()` — highest-consequence first:

1. `combined_caution()` — **Wide-complex tachycardia** when HR > 100 **and** QRS ≥ 120 ms, inserted at the very top. A rate and a width that are dangerous together must not be read as two independent findings, so it leads and carries *"cannot exclude VT vs SVT with aberrancy - physician review required"*.
2. **ST findings** from `measurements["st_mm"]` — diffuse elevation, elevation by territory (anterior / lateral / inferior, with reciprocal change noted), suspected posterior extension, and ST depression.
3. **The rhythm and interval findings** passed in as `conc_list`.
4. **`Artifact in lead(s) …`** appended last, when a lead's high-frequency ratio exceeds 0.012 — the same measurement the muscle filter's QRS gate is keyed to, so one number drives both the filtering decision and what the report admits to.

**Sizing.** The box grows upward from a fixed bottom edge, height clamped to 15–24 mm,
so it can never collide with the brand line however many findings there are. Any row
that would cross the bottom border is dropped rather than printed outside it — the
test is on the text height (~2.8 mm), not a whole row, so the last line is not thrown
away for the sake of the gap beneath it.

### The permitted findings

Only these eight labels can print. They are defined once as
`REPORT_ALLOWED_CONCLUSIONS` in [ecg_report_generator.py:1689](src/ecg/ecg_report_generator.py)
and print in this order; the thresholds live in
[interpretation.py](src/ecg/interpretation.py) so the report and the dashboard cannot
publish different definitions of "normal" for the same measurement.

| # | Finding | Fires when | Criterion printed |
|---|---|---|---|
| 1 | Normal Sinus Rhythm | HR 60–100 | `V-rate 72, 60-100` |
| 2 | Sinus Bradycardia | HR < 60 | `V-rate 58, < 60` |
| 3 | Sinus Tachycardia | HR > 100 | `V-rate 118, > 100` |
| 4 | Narrow QRS | QRS 70–109 ms | `QRSD 92, < 110mS` |
| 5 | Short QRS duration | QRS < 70 ms | `QRSD 64, < 70mS - verify signal` |
| 6 | Borderline QRS duration | QRS 110–119 ms | `QRSD 116, 110-119mS` |
| 7 | Wide QRS | QRS ≥ 120 ms | `QRSD 132, >= 120mS` |
| 8 | Prolonged QTc | QTc ≥ 460 ms | `QTc 486, >= 460mS` |

Every one derives from a value that is also printed in the report header (HR, QRS,
QTc), which is the property that lets a reader verify it on the same page. `Narrow
QRS` is the normal band; `Short QRS duration` is reported because a QRS that short is
outside physiological range and in practice usually means the onset/offset detection
is clipping a weak signal — which the reader needs to know either way.

**Variants fold in rather than being dropped**, so a real finding is never lost to
wording alone (`_CONCLUSION_CANONICAL`): `Sinus Rhythm` → `Normal Sinus Rhythm` (the
bare form emitted when P waves are undetected), `Bradycardia` / `Tachycardia` → the
sinus forms, `IVCD` / `Intraventricular conduction delay` → `Borderline QRS
duration`, `Normal QRS` → `Narrow QRS`, and `Long QT Syndrome` → `Prolonged QTc`
(QTc > 500 is still prolonged). A finding carrying its own evidence — `Prolonged QTc
(486 ms)` — has the value stripped before matching.

### What deliberately does not print

Asystole · Ventricular Fibrillation · Ventricular Tachycardia · Atrial Fibrillation ·
Atrial Flutter · any AV block · any bundle branch block · PVC / PAC · Short PR ·
Borderline QTc (440–459 ms)

**Stated plainly:** the report will not name these even when the analyser detects
them. The morphology and rhythm classifiers proved unreliable in the field — a normal
65 bpm sinus ECG was printed with a conclusion of *"Ventricular Fibrillation"* — and a
wrong lethal label on a signed report is worse than no label. The full waveform is
still printed and every interval is still measured and shown in the header;
interpretation beyond rate, QRS width and QTc is left to the reading clinician. **The
live on-screen analysis is unchanged** — this is a printing restriction, not a
detection one.

ST findings are the exception to the list above: they are excluded from
`REPORT_ALLOWED_CONCLUSIONS` but reach the box through `st_findings()`, which is a
separate per-lead measurement path rather than a classifier verdict.

### The pipeline, end to end

1. `twelve_lead_test.generate_pdf_report()` builds `conc_list` from the live dashboard analysis, then adds QTc entries from the measured value.
2. Status lines — `No cardiac activity detected`, `Rate below measurable range`, `No ECG data available`, `Please connect device` — are set aside. They are not findings and must survive filtering.
3. QTc wordings are canonicalised to `Prolonged QTc`. `Borderline QTc` is deliberately **not** mapped: 440–459 ms is below the 460 ms the permitted label means.
4. `restrict_to_allowed_conclusions()` folds variants and drops everything off-list.
5. **Empty-box guard.** If everything was filtered out but a heart rate was measured, the rate is restated (`ensure_rate_conclusion()` does the same for the other generator). An empty box reads as *"nothing found"* rather than *"we are not reporting that class of finding"*, which is the more dangerous of the two.
6. Hard cap at 5, applied **after** the filter — capping before it would cap labels rather than remove them.
7. `ecg_report_android.generate_report(conc_list=…)` → `build_interpretation()` → the box is drawn.

### Known gaps

- **`severity` is computed but never drawn.** `classify()` returns `NORMAL ECG` / `BORDERLINE ECG` / `ABNORMAL ECG` / `UNINTERPRETABLE ECG` and `build_interpretation()` returns it under `severity`, but no renderer reads the key — `grep severity src/ecg/ecg_report_android.py` returns nothing. The module docstring shows `- ABNORMAL ECG -` as part of the intended layout, so the box is currently missing the line that classifies the tracing as a whole. Commercial carts print it.
- **`axis` is computed but never drawn.** P / QRS / T axis is returned in the same dict and dropped.
- **`tests/test_report_conclusions.py` is out of date.** It still asserts the permitted set is exactly five labels and that `Bradycardia (non-sinus)` / `Tachycardia (non-sinus)` are removed entirely; both changed when the three QRS-duration labels were added and the non-sinus forms were mapped to the sinus ones. Four tests fail as a result (`python -m unittest tests.test_report_conclusions`). The source is correct and the test file needs updating to the current eight-label set.

---

## 📋 Changelog

### 🩺 [2026-08-29] — Muscle Filter Left a False J-Point Depression on the Chest Leads

At the 25 Hz setting a lead too noisy to gate fell all the way back to the plain
low-pass, running the cutoff straight across the QRS. Measured on
`recordings/raw_all_leads_20260827_120820.csv`: the J point dropped **0.54–1.12 mm
in V1–V6** (worst V3) while the clean limb leads on the same recording moved
**0.000 mm**, and 20–29% of the QRS peak-to-peak was lost in those same leads.

#### Why it mattered more than the millimetres suggest
The gate is decided per lead from that lead's own noise, and the chest leads are
the noisy ones far more often than the limb leads are. So the artifact was not
spread evenly across the page — a J-point depression sitting on V1–V6 with I–aVF
at exactly zero has the shape of a regional finding and reads as anterior
ischaemia. The voltage loss lands on Sokolow-Lyon (SV1 + RV5), which the report
prints. No new notch was invented; what moved was the *level* of the J point.

The automatic ST reading was never fooled — `interpretation.py` measures at
J+60 ms, where the error is ≤ 0.02 mm. It was the printed waveform that misled.

#### Four changes
- **`EMG_GATE_FALLBACK_HZ = 100.0`.** The QRS is protected either way; the noise
  now decides what it is protected *with* — the untouched trace on a clean lead, a
  100 Hz version on a noisy one. Never narrower than the operator's own setting.
  V3 @ 25 Hz: **−1.115 mm → +0.147 mm**. V1 QRS retention: **70.6% → 92.3%**.
- **Default `filter_emg` 25 → 150 Hz.** The IEC 60601-2-25 diagnostic bandwidth.
  Measured across the 116 reports captured 2026-08-28/29, on the 1057 of 1392 leads
  whose raw J point is stable enough to measure: 150 Hz shifts ST by at most
  0.044 mm, 25 Hz by at most 0.140 mm — both far inside a clinically read amount
  now that the fallback is fixed. 150 Hz is chosen for the margin and the standard,
  not to rescue a broken setting. Existing installations keep their own setting —
  new installs only.
- **The report now names the smoothed leads.** `artifact_statement()` could always
  print them, but nothing ever populated `frozen["lead_noise"]`, so it returned
  `""` on every report. It is now filled from `lead_noise_ratio()`, the same
  measurement the gate switches on.

#- **The gate mask was covering the T wave too.** `detect_qrs_regions()`
  thresholded at the 75th percentile of |signal| with a 300 ms peak gap, so at
  59 bpm the T wave registered as a second R peak — 20 peaks for 10 beats in 8 of
  12 leads, a mask over 32% of the record. The muscle filter handed the T wave
  back unfiltered, mains ripple included, which is why a 25 Hz print looked fuzzy
  beside a commercial cart's at the same setting. Now uses the module's own R-peak
  criterion and a ±60 ms window: **visible out-of-QRS fuzz down 76%** (9.44 →
  2.26 µV rms across 480 leads).

### 🧪 Verification — `tests/test_filters_jpoint.py` (9 tests)
Compares the fallback against the plain low-pass it replaced rather than against a
constant, so the test fails if the old behaviour returns. On the noisy fixture at
25 Hz: old 0.660 mm J shift / 82.3% QRS, new 0.034 mm / 99.6%. Clean leads pinned
unchanged, and the gate's threshold pinned to the ratio the report prints from.

Also measured: the full chain passes the IEC frequency-response (+0.4/−3.0 dB
across 0.05–150 Hz) and impulse-response (0.027 mV displacement, 0.000 mV/s slope
against 0.1 mV / 0.30 mV/s limits) tests. Details in **The Filter Chain** above.

### ⏱️ [2026-08-24] — Stale Metrics: A Rate Change No Longer Leaves the Old Numbers on Screen

Reported with a Fluke simulator: set to 72 bpm, then switched to **3 bpm**. The 12-lead page kept showing **BPM 71 / PR 149 / QRS 92 / QT 317** indefinitely while all twelve traces were visibly flat, and a report generated in that state printed the same numbers next to a conclusion of *"Asystole"*.

#### The measurements were right; two display layers were lying
At 3 bpm the RR interval is 20 s, and the analysis buffer is `HISTORY_LENGTH = 10000` samples — exactly 20 s at 500 Hz. **At most one R-peak can ever be in the window**, and `calculate_all_ecg_metrics()` needs three, so the pipeline correctly returned zero. Roughly **9 bpm is the slowest rate it can express at all**.

The stale numbers came from two independent "hold last good value" layers, each answering every failed window with the previous measurement, and **neither had an expiry**:

1. **`src/ecg/ui/display_updates.py`** — every metric falls back to `_last_valid[...]` when the incoming value is 0. One good reading was echoed for as long as the page stayed open.
2. **`twelve_lead_test.calculate_ecg_metrics`** — `pr_interval_raw` / `qrs_duration_raw` / `qt_interval_raw` fell back to the previous attribute, and the median-beat early-return path (the branch a very slow rate takes on *every* tick) re-published them without ever writing a new value.

A hold is right for a momentary dropout — one missed beat, one noisy window. It is wrong for a sustained inability to measure. Both layers are now bounded at **4 seconds**, deliberately the same figure on both sides so the page and the labels cannot disagree about whether a value is still valid. Below the pipeline's own ~9 bpm floor there is no plausible single-window dropout to protect, so nothing is lost.

Verified on the real page: `72 bpm → HR 72 / PR 158 / QRS 81 / QT 338`, switch to 3 bpm → **all zero**, back to 72 bpm → **values return**. A single-window dropout still smooths over without a flicker.

`reset_metric_holds()` replaces the ad-hoc `_last_valid.pop(...)` loop in the flat-line path, so a pre-arrest number cannot be echoed back through the hold window after signal loss.

#### A third state: rate below the measurable range
At 3 bpm the trace is **not** flat — QRS complexes are plainly present — so this is neither asystole nor a disconnected lead, and reporting *"No ECG data available / Please connect device"* would send the operator after equipment that is working correctly while the patient has a profoundly slow rhythm.

The page now flags `_rate_below_measurable` when R-peaks are present but too few to measure, and the report distinguishes all three:

| Trace | Report says |
|---|---|
| electrodes off, flat | No ECG data available / Please connect device |
| electrodes on, flat | No cardiac activity detected / All measurements zero - review trace |
| R-peaks present, too few | Rate below measurable range / Review trace - measurements unavailable |

#### 🧪 Verification — `tests/test_stale_metric_holds.py` (20 tests, 12 subtests)
- The rate-floor arithmetic pinned: 20 s window, one peak at 3 bpm, three needed.
- Display hold: a brief dropout is smoothed over; a sustained zero falls through to 0; an expired hold is *discarded*, not merely hidden; recovery works.
- Page hold: source assertions that the unbounded `getattr` fallbacks are gone and cannot be reintroduced, that the median-beat early-return path expires its holds, and that the two hold windows match.
- Behavioural, real `ECGTestPage` in a clean subprocess: 72 → 3 → 72 bpm, including a check that `get_current_metrics()` (what the report reads) does not return a held value.
- The report's three states are mutually exclusive, and the low-rate branch is asserted not to mention the cable.

Full suite: **398 passed, 255 subtests**.

> **Note for testing:** these are source changes, so a running instance must be restarted to pick them up. The report in the original bug screenshot was produced by a session started before this work and still shows the old behaviour, including the `Asystole` conclusion that the findings allow-list now filters.

### 🫀 [2026-08-21] — Asystole Now Reads Zero Everywhere (Was Showing Pre-Arrest Values)

During asystole every measurement now reads **0** on the 12-lead page, on the dashboard and in the PDF. Previously the numbers from before the arrest stayed on screen next to a flat trace.

#### The bug
The 12-lead page already had a flat-line guard that zeroed every metric — but it was gated on `and not limb_active`, so it only fired when the limb leads were reported **disconnected**. That is exactly backwards for asystole: a flat trace with the electrodes still on the patient *is* asystole, and it was the one case the guard refused to handle.

The pipeline then ran on a flat signal, found no R-peaks, and every downstream "hold last good value" fallback re-published the pre-arrest numbers. Measured on the real page: **HR 72, PR 158, QRS 82, QT 338, QTc 370, RR 834 all survived** the transition to a flat trace. A flatline was drawn beside a live-looking heart rate.

#### The fix
Flatness alone now drives the guard. `_raw_std_ii` is in ADC counts and is evaluated *after* the existing Lead I fallback, so `< 5.0` means both limb leads are flat — no real ECG carrying a QRS has a standard deviation of five ADC counts. Either the electrodes are off or the heart is not beating, and in both cases there is nothing to measure.

The zeroing block was also incomplete. It now clears **QTcF, ST, the axes, the amplitude figures and the pending/deadband state** as well — any value left behind is a pre-arrest number displayed as though it were current, and a held deadband value could be promoted onto the display one tick after signal returned.

#### The report must not call asystole a cable fault
Both kinds of flat trace zero the metrics, but they mean very different things:

| | meaning | report says |
|---|---|---|
| electrodes **off**, flat | a device problem | *No ECG data available / Please connect device* |
| electrodes **on**, flat | no cardiac output | *No cardiac activity detected / All measurements zero - review trace* |

The page sets `_asystole_active` to distinguish them, and the report reads it. Sending an operator to check a cable that is fine, while the patient has no cardiac output, is worse than saying nothing. Neither line is a rhythm diagnosis, so neither is subject to the findings allow-list — they are status text, like the existing no-data message.

#### A bypass in the conclusion allow-list, found while doing this
The zero-data safeguard branch appended `_build_metric_conclusions()` output **directly** to the conclusion list, skipping `_normalize_report_conclusions()` entirely — so labels the allow-list is meant to filter reached the printed report through this path. Confirmed leaking: `Third-degree AV Block`, `Borderline Wide QRS`, `First-degree AV Block (Prolonged PR)`, `Long QT Syndrome`. The branch now merges through the normaliser like every other path. Swept 576 value combinations through it: zero off-list labels.

#### 🧪 Verification — `tests/test_asystole_zeroing.py` (14 tests, 13 subtests)
- **Behavioural, on a real `ECGTestPage`** in a clean subprocess (the rest of the suite stubs PyQt5, so real Qt cannot be built in-process): real signal → HR 72; asystole with electrodes attached → every metric 0, `_asystole_active` True, every on-screen label reading 0; signal returns → HR 72 and the flag clears. No value sticks in either direction.
- **Dashboard** confirmed to read `'0'` for HR, PR, QRS, QT, QTc and RR through `get_current_metrics()` during asystole, and the `live_hr` path reads 0.
- Source-level assertions that the `and not limb_active` gate is gone, the flag is set and cleared, every metric attribute is zeroed, and the report's two messages are mutually exclusive.
- The allow-list bypass pinned shut, including a test that the raw `dashboard_conclusions.append(mc)` pattern is not reintroduced.

Full suite: **378 passed, 243 subtests**.

### 📋 [2026-08-21] — Report CONCLUSION Restricted to Five Value-Derived Findings

The printed conclusion box on the 12-lead report (both 12×1 and 6×2 layouts) now carries exactly these and nothing else:

**Normal Sinus Rhythm · Sinus Bradycardia · Sinus Tachycardia · Wide QRS · Prolonged QTc**

All five derive from a measurement that is also printed in the report header, so a reader can check every conclusion against the numbers on the same page.

#### Why
The morphology and rhythm classifiers proved unreliable in the field — a normal 65 bpm sinus ECG with a 152 ms PR interval was printed with a conclusion of *"Ventricular Fibrillation"*. A wrong lethal label on a signed report is worse than no label.

**Consequence, stated plainly:** the report no longer names Asystole, Ventricular Fibrillation, Ventricular Tachycardia, Atrial Fibrillation, Atrial Flutter, any AV block, any bundle branch block, PVC/PAC, ST elevation/depression, or Borderline Wide QRS — even when the analyser detects them. The full waveform is still printed and all intervals are still measured and displayed; interpretation beyond rate, QRS width and QTc is left to the reading clinician. The live on-screen analysis is unchanged.

#### How
- `REPORT_ALLOWED_CONCLUSIONS` plus `restrict_to_allowed_conclusions()` applied at the end of `_normalize_report_conclusions()` — the single funnel every conclusion source in the module passes through, so no path can bypass it. The 6×2 generator calls the same helper, so the two layouts cannot drift apart.
- **Variants of a permitted finding are folded in, not dropped**, so a real finding is never lost to wording: `Sinus Rhythm` → `Normal Sinus Rhythm` (the bare form emitted when P waves are undetected), `Bradycardia`/`Tachycardia` → the sinus forms, and `Long QT Syndrome` → `Prolonged QTc` (QTc > 500 is still prolonged; the permitted wording is used).

#### Two defects found and fixed while doing it
- **A QRS of 116 ms printed no QRS finding at all.** The value rules only ran as a last-resort fallback, so whenever any earlier source supplied a rhythm label the interval findings were never computed. They are now derived unconditionally and merged.
- **A QRS of 116 ms then printed an *empty* box.** "Borderline Wide QRS" set the internal `abnormal` flag, which suppressed "Normal Sinus Rhythm", and the allow-list then removed Borderline as well — leaving nothing. The flag is now computed only from findings that will actually be printed, and Wide QRS / Prolonged QTc are excluded from it: they are conduction and repolarisation findings, not competing rhythm diagnoses, so `Normal Sinus Rhythm` + `Wide QRS` is a coherent pair and the rhythm line stays.
- **A profoundly bradycardic patient could get a blank box.** Below 40 bpm with no measurable PR the rules pick `Third-degree AV Block`, which is now filtered out. `ensure_rate_conclusion()` restates the rate finding so the box is never empty when a heart rate was measured — using the same wording the rules already use at 40–59 bpm, so it makes no claim they were not already making.

#### Capacity
Maximum output is **3 findings** (one rhythm + optional Wide QRS + optional Prolonged QTc) against a box that prints **4 rows**, so nothing can ever be cropped. Previously the ladder could rank 24 labels into 4 slots, and 21 of the labels the detectors emit were unranked — they sorted to the very end, which is how a `3rd-degree AV block` could be pushed off the page beneath `Prolonged QTc`.

#### 🧪 Verification — `tests/test_report_conclusions.py` (17 tests, 39 subtests)
- 30 blocked labels each confirmed removed, individually and when mixed with a permitted one.
- 9 spelling variants confirmed folded to the permitted wording.
- **Exhaustive 6,912-combination sweep** of HR × PR × QRS × QTc: zero empty boxes, zero overflows past 4 rows, zero off-list labels, sizes only ever 1–3.
- Threshold boundaries pinned (QRS 119 vs 120, QTc 460 vs 461) and all three field reports reproduced.

One pre-existing test in `test_cardiox_prod.py` asserted the old behaviour — that complete heart block survives and suppresses the rhythm line. It is superseded by this policy and has been updated in place with the reason recorded, rather than deleted.

Full suite: **364 passed, 230 subtests**.

### 🚨 [2026-08-21] — "Ventricular Fibrillation" Reported on a Normal Sinus ECG

A 12-lead PDF was produced reading **HR 65 bpm, PR 152 ms, QRS 106 ms, QT 346 ms, QTc 359 ms**, with twelve leads of visibly organised, narrow-complex, P-wave-bearing sinus rhythm — and a CONCLUSION of **"Ventricular Fibrillation"**. This is the most dangerous output this application can produce, and the report contradicted itself: VF is disorganised ventricular activity with no atrial-to-ventricular conduction, so there is no PR interval to measure, no organised QRS to time, and its ventricular rate is 150–400 bpm.

#### The failure chain
1. **`is_ventricular_fibrillation()` can reach a VF verdict with no fast beat at all** (`src/ecg/arrhythmia_detector.py:745`). It scores four criteria and fires at ≥ 0.60, but the **rate** criterion is worth only 0.35. RR-variability (0.30) + amplitude-variability (0.20) + baseline-chaos (0.15) = **0.65** — over the line, entirely from noise. Confirmed by measurement: synthetic sinus at 65 bpm with EMG-grade noise and variable R amplitudes scored 0.65 with the rate criterion contributing nothing.
2. **The backstop existed and was bypassed.** `physiological_consistency` Rule 4 is written precisely to catch this — *"organised QRS + reliable HR contradicts VF"* — but was skipped whenever `vf_score >= 0.5`, under the comment *"Strong VF evidence — never suppress"*. A score of 0.5–0.65 reached without any fast beat is not strong VF evidence; it is noise.
3. **The bypass also erased the evidence.** `vf_score > 0.6` additionally forced `organized_qrs = False`, so even had Rule 4 run, the input it needed was already gone.

#### The fix — two independent layers, both conservative toward real VF
- **Detector (`arrhythmia_detector.py`):** an organised-rate gate. If fewer than 35% of RR intervals are ≤ 450 ms **and** the median RR implies 20–150 bpm, the rhythm is organised and VF is refused regardless of the noise score. Genuine VF is unaffected — its RR intervals are short and chaotic, so the gate never fires. Verified across VT 180 bpm, VF ~250 bpm, VF ~330 bpm and coarse VF with long gaps: the gate stays inactive for all of them, and fires for sinus at 65 / 73 / 91 bpm.
- **Consistency backstop (`physiological_consistency.py`):** hard contradictions now outrank the score. A **measured PR interval** at an organised rate proves AV conduction and vetoes VF at *any* `vf_score`; a **narrow organised QRS** (< 120 ms) at an organised rate does the same. A high score no longer erases a positively-measured narrow QRS.

#### 🧪 Verification — `tests/test_vf_false_positive.py` (16 tests, 29 subtests)
Both directions are pinned, because silencing genuine VF would be far worse than the bug being fixed:
- **False positives blocked:** the exact reported case; organised rhythms at 40–140 bpm; a 72-case sweep of noise (60–200 µV), amplitude jitter and imperfect peak detection at 65 bpm — zero VF verdicts; a measured PR vetoes VF at every score from 0.5 to 1.0.
- **Genuine VF preserved:** nothing measurable; 280 bpm with no conduction; 200 bpm wide-complex with no PR; rates 160–350 bpm. All still reported. Asystole and VT are untouched.
- The scoring-structure test documents *why* a gate was added rather than nudging the 0.60 threshold: raising it to 0.66 would have masked this one path while leaving a VF verdict reachable with no fast beat.

**Honest limitation:** the recording behind that PDF was not saved locally (the newest stored report predates it), so the exact signal could not be replayed. The synthetic reproduction reached the 0.65 score but was caught by an unrelated atrial-flutter heuristic, which is a fragile accident rather than a designed guard. The fix therefore rests on the structural argument and on the report's own internal contradiction, not on a bit-exact replay. **Re-generate a report on real hardware to confirm the conclusion now reads correctly.**

### ⚡ [2026-08-21] — Live-Path Responsiveness: Stop the UI Freezing on Ordinary Hardware

Reported as *"waves coming from hardware and it gets freeze cluttered"* on a normal PC. A six-subsystem audit of the live path (buffer writes, rendering, serial threading, timer budgets, memory growth, blocking calls) produced 30 candidate causes; each was handed to a separate reviewer whose job was to **refute** it. 16 survived, 14 were refuted — including the first one that looked obvious, which is why the list below is not the one anyone would have guessed.

#### ✅ The actual freeze: lead-off detection ran once per lead **per sample** (`src/ecg/hyperkalemia_test.py`)
- `detect_lead_off()` sat inside the per-lead loop inside the per-packet loop — **6,000 whole-window analyses per second** on the Qt main thread. Each call copied a 500-sample deque to a float64 array and ran `ptp`, `var`, `diff`, `flatnonzero`, `concatenate`, `argmax`, `median`, `min` and `max` across it.
- Measured: the write loop cost **414 ms of work per second of streamed data — 41% of one core** — of which lead-off was **91%**. A single 30 ms tick cost 12 ms at rest and **70 ms while catching up**, so the event loop simply stopped dispatching paint events. That is the freeze.
- The window still receives every sample; only the verdict moved to once per tick (~400/s instead of 6,000/s). The debounce counters now advance by the tick's **sample count** rather than by one, so thresholds stay in sample units and the 0.5 s engage / 0.2 s release timing is preserved exactly — converting them to tick counts would have silently retuned the debounce on precisely the slow machines this work targets.
- The `len(w) >= 50` guard also bought a guaranteed-`False` answer at the price of an array copy, since the detector returns `False` until it has a full 1 s window. Now gated on the real window length.
- **Result: 414 ms/s → 32 ms/s (41% of a core → 3.2%). A 100-packet catch-up tick: 70 ms → 0.77 ms.**

#### ✅ `np.roll` per lead per sample — real, but *not* the freeze
- Every sample rebuilt twelve 40 KB arrays to advance a write cursor by one: ~240 MB/s of memcpy and ~6,000 ndarray allocations per second, whose collection produced a measured 10–13 ms hitch roughly every 12 s.
- Honest scoping: this was the first thing found and it looked like the culprit. Reviewed properly it is **~1 ms of a 30 ms tick at rest** — a stutter contributor, not a freeze. It only overruns the tick during a 500-packet backlog (33.5 ms). Recorded here because the measurement that demoted it is the reason the real cause was found.
- Fixed by staging each tick's samples and committing them with one in-place memmove plus one tail write per lead. **Deliberately not** the index-addressed ring the audit recommended: `self.data` has 63 readers in one file and 27 more across the package, all assuming "chronological, newest at `[-1]`". A ring breaks that assumption *silently* — no crash, just a wrong clinical measurement read from a wrapped buffer. The batched write keeps the layout byte-identical.
- Verified numerically identical to the old per-sample roll across batch sizes 1 → 25,000, including the overflow case where a batch exceeds the buffer.
- Applied to the 12-lead packet path, the legacy line reader, both HRV calculator writes, HRV's own display buffer, and the hyperkalemia calculator buffer (whose display ring had been fixed previously but whose analysis buffer had not). **1 ms → 0.12 ms at rest; 35 ms → 0.16 ms on a 500-packet tick.**

#### ✅ 13.6-second freeze when opening the HRV / Hyperkalemia pages (`src/ecg/serial/hardware_commands.py`)
- `_read_packet()` read **one byte** per loop and then slept `0.01 s` — with the sleep *outside* the `in_waiting` check, so it ran after every successful read too. CPython's sleep granularity on Windows is ~15 ms, giving roughly **65 bytes/s against a device streaming ~11,000**. The handshake could never reach its ACK and burned the entire timeout on the GUI thread.
- Now reads in bulk and sleeps only when the port is genuinely empty. **The framing state machine is byte-for-byte unchanged** — proven by replaying 3,000 random byte streams through both the old and new framers at five chunk sizes (15,000 comparisons, zero mismatches), so frame detection cannot have shifted.
- ⚠️ **Needs a hardware test.** The measurement behind the 13.6 s figure was taken against a present-but-silent mock. The arithmetic holds independently, but this is the device handshake and it must be exercised against a real RhythmUltra — both streaming and absent — before release.

#### ✅ The "cluttered" trace: overlay leads drew on top of each other (`src/ecg/twelve_lead_test.py`)
- Three `line.set_clip_on(False)` calls let each overlay lead paint outside its own axes. With `ylim` pinned to the full 0–4095 ADC range and the `+2048` centering, a normal R-wave at 20 mm/mV reaches ~4248 and spills into the lane above — measured **51 spilled pixels at 20 mm/mV, 514 at 40 mm/mV**. One lead's R-waves appearing in another lead's row is the "cluttered" symptom, and it is a *correctness* defect, not slowness: no amount of speeding things up would have fixed it.

#### ✅ Metrics timer stopped monopolising the GUI thread (`src/ecg/twelve_lead_test.py`)
- The heaviest of the three pages was the only one whose timers ignored `is_low_spec_mode()` — so on a weak machine it ran the most expensive callbacks the fastest. Now matches HRV and hyperkalemia (500 ms metrics / 50 ms plot on low-spec).
- Added a duty-cycle self-throttle: the callback measures itself and reschedules so it can never own more than **25% of its own period**. A 90 ms callback reschedules at 360 ms instead of 200 ms rather than deleting plot frames. Same idiom already used for the global QRS refresh.

#### ✅ Screen recording grew at 187 MB/s (`src/ecg/twelve_lead_test.py`)
- `grabWindow()` at 33 fps appended a full-resolution BGR frame to an **uncapped list**: 6.22 MB/frame at 1920×1080 → **~5.6 GB after 30 s**. On an 8 GB machine that swaps the whole process, including the 500 Hz serial drain sharing the thread — a freeze a user would blame on the ECG.
- Now a `deque` capped to a known number of seconds, with wide grabs downscaled to 1280 and the first frame's geometry pinned for the session so a mid-recording resize cannot produce a corrupt video file.

#### ✅ Overlay stopped burning the plot timer (`src/ecg/twelve_lead_test.py`)
- While the 12:1 / 6:2 overlay is up, the pyqtgraph plot area is hidden but the 30 ms timer kept running the full filter → interpolate → `setData` chain for twelve curves into widgets Qt never paints, alongside a matplotlib redraw measured at 44 ms.
- The guard is placed **after** the packet drain and buffer writes, deliberately. Stopping the timer instead would also stop `read_packets()`, the Holter writer push and the BPM push — all of which live in the same callback — so the overlay would have silently stopped recording. Skip the render, never the acquisition.

#### 🚫 Deliberately not changed — signal integrity
- **No sample may be dropped from the write path.** No parse deadline, stride or decimation between the parser and the lead buffers, the Holter writer or the BPM controller. Render is decimated; acquisition never is.
- **`max_iterations` and the 100 KB buffer clear stay** while acquisition is still on the GUI thread. Removing the cap would convert a recoverable backlog into a hard freeze.
- **`setDownsampling(mode='subsample')` must never be enabled** — it takes every Nth sample and clips R-wave peaks. `mode='peak'` only.
- **The display time-base bug is documented, not fixed.** `time_axis` divides by 500 Hz while the data is 1000 Hz post-interpolation. It is currently invisible because the x-range is auto-fitted to the data extent each frame, and correcting it changes mm/s on a clinical trace — that needs a calibration-pulse check against real hardware, not a blind edit.
- Not attempted: the full index-addressed ring, threading `calculate_ecg_metrics`, and moving acquisition to its own thread. All three are high-risk refactors on clinical code, and the plan's own guidance is to re-measure first — the cheap fixes may have already closed the tick.

#### 🧪 Verification
- Batched write proven numerically identical to the per-sample roll (batches 1 → 25,000, including buffer overflow).
- Handshake framing proven unchanged over 15,000 old-vs-new comparisons.
- **Clinical regression gate:** `calculate_ecg_metrics()` on a fixed 12-lead buffer returns HR 72, QRS 94 ms, global-multilead across 12 leads — identical before and after every change.
- Full suite: **330 passed, 1 skipped, 162 subtests** (the skip is the device-serial test, correctly skipping with no hardware attached).

### 🔒 [2026-08-21] — Input Limits, Form Hardening & Auth Security Audit

#### ✅ Shared validation module (`src/utils/input_validation.py` — new)
- The same field was constrained three different ways in three files: the waveform-analysis mobile box capped its **length** but accepted letters, the organisation forms used an integer validator whose ceiling rejected most real mobile numbers, and the legacy signup dialog checked nothing at all. One module now owns every limit, and because it imports no Qt at module scope the whole rule set is unit-testable headlessly.
- **Every rule is enforced twice, on purpose.** At the widget (`apply_digit_only` / `apply_text_limits`) so bad input cannot be typed or pasted; and again at the logic layer (`validate_*`) before the value is stored, uploaded, or used to build a request. The widget layer is a usability convenience and is bypassed by anything that is not the GUI — the logic layer is the one that actually holds.
- Standard limits: phone **exactly 10 digits**; password **8–128**; username 3–64; name 2–100; email ≤254 (RFC 5321); organisation name ≤120; address ≤200; serial ≤64; age 0–120. Every maximum is finite, so no field can be used to push a multi-megabyte string into `users.json`, a PDF, a log line or a cloud payload.
- **Character rules follow reality, not tidiness.** Two rules were written too tight on the first pass and corrected after testing on hardware:
  - **Serial ID is filled in by the device, not typed.** `on_scan_finished()` sets the box read-only from `send_machine_serial_command()`, which returns 16 bytes of raw ASCII from the firmware — a real serial is `DM ECG V1.0 A998`, **spaces and dots included**. An allow-list of `[A-Za-z0-9_-]` refused every genuine device and blocked signup outright. What still applies to a machine-supplied value is the length bound and control-character rejection, because it reaches `users.json`, S3 keys and cloud payloads; the character set now matches the firmware. The *"device connection lost"* placeholder is recognised and stored as empty rather than as a serial.
  - **Names use a deny-list, not an allow-list.** `[A-Za-z0-9 ...]` rejected `Dr. José García`, `Zoë Müller` and `दिव्यांश शर्मा`. In a clinical application used in India, refusing a doctor's own name is a defect, not a security posture. Unicode letters from any script are accepted; only characters that change meaning at one of the value's sinks are refused — `< >` (reportlab Paragraph parses inline markup), `{ }` (template interpolation), `[ ] \` (escaping and paths), `` | ` $ ; `` (shell metacharacters) and `"`. The one narrow exception is a username made **entirely** of non-ASCII digits, since `٩٨٧٦٥٤٣٢١٠` and `9876543210` are different identifiers that look identical on screen.

#### ✅ Waveform analysis — mobile number is digits only (`src/dashboard/analysis_window.py`)
- The field had `setMaxLength(10)` and **no validator**, so `12ab34cd56` could be typed. `_normalize_mobile_no()` then silently reduced it to six digits and the length check rejected it with a message that did not match what the user could see in the box.
- Now digit-restricted at the keystroke, and re-validated with `validate_phone()` before the value is used to build the public-reports API request.

#### ✅ `QIntValidator(0, 2147483647)` rejected most real mobile numbers (`src/organization.py`)
- `QIntValidator` is bounded by a C++ int. Any mobile number above 2147483647 — which is every number starting 3 through 9 — had **every keystroke refused**. Found in **three** places (the profile form, the edit-user dialog, and the create-user form); all now use the shared digit regex, which has no integer ceiling.
- The organisation signup also accepted a phone of *"at most 10 digits"* (so one digit passed), an age with no upper bound, and a 6-character password. All three now use the shared limits.

#### ✅ Non-ASCII digits are no longer accepted as numbers (`src/utils/input_validation.py`)
- `str.isdigit()` returns True for Arabic-Indic numerals, and Python's regex `\d` matches them. A phone typed as `٩٨٧٦٥٤٣٢١٠` therefore passed a ten-character check and would have been sent to the cloud API as non-ASCII text. Digit handling is now explicitly `[0-9]`, and `str.isdigit()` is avoided throughout the module for the same reason.

#### ✅ Login is rate-limited (`src/main.py`)
- The OTP path already locked after 3 failed attempts for 5 minutes. The **password path counted nothing**, so the form accepted guesses as fast as they could be typed. Sign-in now locks after **5 failures for 5 minutes**, per identifier, and the remaining-attempt count is shown before the lock trips.
- The failure message deliberately does not distinguish a wrong identifier from a wrong password — telling them apart turns the form into an account-enumeration oracle.
- This bounds guessing *at the UI*, which is the threat this application can see. It is not a substitute for the PBKDF2 work factor that protects the hash file itself.

#### ✅ Registration validated at the logic layer (`src/auth/sign_in.py`)
- `register_user_with_details()` is where every registration path in the app converges, so the limits are applied there as well as at each form. A caller that forgets to validate — including a future one — still cannot write an unbounded or control-character-laden value into `users.json`.
- `users.json` holds PBKDF2 password hashes and was written with default permissions, readable by every account on the machine. It is now `chmod 600`, best-effort so a permissions failure cannot lose a save that already succeeded.

#### ✅ Path traversal in the Holter session directory (`src/ecg/holter/stream_writer.py`)
- The session folder was built as `output_dir / <timestamp>_<patient name>` with only spaces replaced. A patient name of `../../../../Users/Public/pwned` resolved to `C:\Users\Public\pwned` — outside the recordings directory entirely.
- `sanitize_filename_component()` replaces everything outside `[A-Za-z0-9_-]`, which removes dots, slashes and backslashes in one step so no traversal sequence can survive, bounds the length, and escapes the Windows reserved device names (`CON`, `PRN`, `NUL`, `COM1`–`9`, `LPT1`–`9`).

#### 🔍 Audit findings — what was already correct
Scanned the client, the auth layer and the licence server for the usual classes. These needed **no change**:
- **Password storage** — PBKDF2-HMAC-SHA256, 260,000 iterations, per-user 16-byte salt, compared with `hmac.compare_digest`. Legacy plaintext records are upgraded to a hash on next successful login.
- **SQL injection** — every statement in `src/ecg/holter/session_store.py` is parameterised; no f-string or concatenated SQL anywhere in `src/`.
- **Code-execution sinks** — no `eval`, `exec`, `pickle.load`, `os.system` or `shell=True` in shipped code.
- **Transport** — no `verify=False`; TLS verification is never disabled.
- **Secrets** — AWS credentials come from environment variables, never literals; `.env` is gitignored and untracked.
- **Auth flow** — server-first validation with a 7-day offline grace window; the licence gate fails closed; `sign_in_user_allow_serial()` is a misleading name for a function that only ever checks the password hash — there is no serial-as-password bypass.

#### 🧪 Verification
- New suite `tests/test_input_validation.py`: **144 tests, 149 subtests**, all headless. Covers each validator's boundary values (min, min−1, max, max+1), SQL/script/traversal/CRLF payloads in every free-text field, Unicode-digit handling, the rate limiter's lockout / expiry / per-identifier isolation, and source-level assertions that each form actually calls the shared rules — a rule that is not wired in protects nothing.
- The suite found two defects while being written: two further `QIntValidator(0, 2147483647)` phone fields beyond the one first fixed, and `apply_digit_only()` skipping the length cap when validator construction failed.
- Qt behaviour confirmed against a real `QLineEdit`: `9876543210` accepted, `98765abcde` / `abcdefghij` / `12ab34` / 11 digits all rejected at the keystroke.
- Full suite: **324 passed, 156 subtests** (180 pre-existing, unchanged). The serial and name rules are now pinned by regression tests that use the real device serial from `ecg_settings.json` and real non-ASCII names, plus a test asserting that every character in the forbidden set is genuinely matched — hand-escaping a class containing both a backslash and a pipe is easy to get subtly wrong, and that mistake was present until the test caught it.

### 🔧 [2026-08-21] — Multi-Lead Global QRS Boundary (12-Lead, HRV & Hyperkalemia)

#### ✅ QRS width was measured on Lead II alone (`src/ecg/qrs_detection.py`, `src/ecg/ecg_calculations.py`)
- A single lead only sees its own projection of the depolarisation wavefront, so its onset is late and its offset early. The earliest deflection and the latest return-to-baseline almost never occur in the same lead, which is why a Lead-II-only width reads roughly **10–20 ms short** of the true QRS — and why a borderline 118 ms complex could be reported as narrow.
- `compute_global_qrs_duration_12lead()` implements the boundary rule the 12-lead carts use (Glasgow / Marquette): the Curtin 2018 delineation is run **independently on every supplied lead** using Lead II's R-peaks as the shared per-beat anchor, then per beat the width is taken from the earliest onset across leads to the latest offset across leads.
- **Outliers cannot inflate the result.** Taken literally, "earliest" and "latest" mean min and max, so one noisy lead out of twelve would widen every beat. The extremes are replaced by the **15th / 85th percentile** of the lead ensemble — still its outer edge, but immune to one or two bad leads. Across beats the **median** is used, so an ectopic beat cannot drag the measurement either.
- **Leads that cannot contribute are dropped, not averaged in:** a lead shorter than 2 s, one whose peak-to-peak is below 0.05 mV, one the connection tracker has marked off, or one whose buffer length does not match Lead II's (the boundary rule is only valid on a shared sample clock). Below two usable leads the function returns `None` and the caller keeps its existing single-lead measurement — so a one-lead capture behaves exactly as before.
- `calculate_all_ecg_metrics()` takes a new optional `all_lead_data` argument and now reports `qrs_method` (`"global-multilead"` / `"single-lead"`) and `qrs_leads_used` alongside the width. Existing callers that pass only Lead II are unaffected.

#### ✅ Wired into all three clinical pages (`src/ecg/twelve_lead_test.py`, `src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`)
- The 12-lead page hands every connected, non-flat lead to the metrics entry point. Because the HRV and hyperkalemia windows both drive a hidden `ECGTestPage` as their calculator, they inherit the global measurement through the same path — HRV from the leads it feeds (I, aVF, V1, V5, II and the selected lead), hyperkalemia from all twelve.
- **The QRS blend no longer undoes the correction.** The 12-lead page previously mixed the Curtin width 70/30 with a Lead-II median-beat width; applied to a global measurement that would drag it back toward the single-lead under-estimate it exists to correct. The blend is now skipped when the global path produced the number.
- Each page's QRS card carries a tooltip naming the measurement and the lead count, so a global width and a Lead-II width are no longer indistinguishable on screen.
- The hyperkalemia serum-K estimate reads the same width, so its QRS-widening term now works from the global measurement without any change to the estimator.

#### ✅ Cost kept off the UI thread's critical path (`src/ecg/ecg_calculations.py`)
- Delineating twelve leads costs ~30 ms and the pages recalculate metrics from a **200 ms** timer — recomputing every tick would spend a sixth of that budget re-measuring a value that moves on the scale of seconds and is median-smoothed over 15 beats downstream.
- The global result is cached per `instance_id` and refreshed on a **self-tuning interval**: whatever the measurement costs on the machine it is running on, it is scheduled to occupy at most ~5 % of wall-clock time, clamped to 1–4 s. Measured on this hardware: **12.8 ms mean / 39 ms peak** per tick, against a 9 ms single-lead baseline. Failures are cached too, so an undelineatable lead set is not retried five times a second.
- The cache is cleared alongside the interval smoothing buffers when leads drop, so a width measured before a disconnection cannot reappear seconds later.

#### 🧪 Verification
- Synthetic 12-lead case where no single lead sees the whole complex (true width 110 ms): **Lead II alone 75 ms → global 103 ms across 12 leads**.
- Through `calculate_all_ecg_metrics()`: 89 ms single-lead → 94 ms global, with HR, PR and QTc unchanged.
- Through a real `ECGTestPage`: global path taken, 12 leads used, tooltip populated; a lead marked off and a lead held flat were both excluded from the ensemble.
- Degenerate inputs (flat leads, one lead, no R-peaks, empty or malformed lead map) all fall back to the single-lead measurement rather than raising.
- Full suite: **180 passed**. The 3 pre-existing failures in `src/ecg/test_qrs_paper.py` are unchanged — they fail identically at the previous commit and concern `measure_qrs_duration_paper`, which this work does not touch.

### 🔧 [2026-08-13] — Licence Re-Sync, Doctor-Review Upload, Lead-Off Detection, Report Strips & Live Display

#### ✅ Login loop after signup (`src/auth/sign_in.py`, `src/main.py`, `src/utils/license_manager.py`)
- **Double registration removed:** signup called `/register` twice — once via `license_manager.register_device()` (whose token is saved to `cardiox.lic`) and again from `register_user_with_details()`. The server moved the machine onto a new seat and deactivated the first, so every later heartbeat answered `SEAT_INACTIVE`.
- **Error code parsing:** `run_startup_checks()` read only `error_code`, but the licence Lambdas put the code in `error`. Every refusal collapsed into the `LICENSE_BLOCKED` fallback, which the login gate reported as *"Your device seat was not found"* and offered to fix by wiping the licence — creating another seat and repeating the failure on the next login.
- **Silent repair:** added `is_stale_seat_error()` and `resync_token_from_credentials()`. A stale token is refreshed from `/validate` using the credentials just entered and the checks re-run, with no dialog. Startup defers to the login screen instead of prompting.
- **Credential form:** `validate_with_credentials()` sends the SHA-256 form that `register_device()` used, retries the raw password for seats created by older builds, and falls back to the registered phone when the typed identifier resolves an old seat.
- **`SEAT_INACTIVE` is no longer treated as revocation** in `sign_in`, which previously deleted the local account and wiped the licence over an out-of-date token.

#### ✅ Doctor-review upload — HTTP 404 "Old Report not supported" (`src/utils/cloud_uploader.py`)
- S3 keys were built from upload-time state: `datetime.now()` for the date segment and the *currently connected* RhythmUltra for the device folder, falling back to `0000`. A report recorded on the 10th but uploaded on the 12th was filed where the review Lambda never looks, and each retry repeated the mistake — one report appeared six times under the wrong prefix.
- `_report_identity()` / `_report_location()` now derive both the device and the date from the report's own filename (`<DEVICE>_<YYYYMMDD>_<HHMMSS>`), covering all three filename formats the backend accepts, and `send_for_doctor_review()` takes its `deviceId` from the same resolver so the upload and the assignment cannot disagree.

#### ✅ Lead-off false positives (`src/ecg/lead_off_detection.py`, `src/ecg/smooth_display.py`, `src/ecg/hyperkalemia_test.py`)
- Thresholds fired on healthy signal. Across 857 clean one-second windows from this hardware, leads reach 3444 ADC p-p and a variance of 360,460 — above the old `amplitude_max` 3000 and `variance_max` 250,000 — and the absolute `min <= 10` rule marked the derived leads (III, aVR, aVF) disconnected for entire recordings, aVR permanently. Because a lead-off verdict substitutes a constant in the display, the analysis buffer **and** the recording, this printed flat strips into reports.
- Rewritten around three real signatures: flatline, sustained pinning at the signal's own extreme, and runaway variance. **0 false positives** on all 857 clean windows, with flat, dithered-flat, rail-clipped and runaway-noise signals still detected.
- `smooth_display.py` carried a private copy of the same broken thresholds; it now delegates to the shared detector.
- The hyperkalemia window latches a verdict only after **0.5 s** of continuous agreement and releases after 0.2 s, so a motion artifact can no longer blank a lead.

#### ✅ Report waveform strips (`src/ecg/ecg_report_generator.py`, `src/ecg/6_2_ecg_report_generator.py`, `src/ecg/ecg_report_android.py`)
- **Edge tapers removed.** `stabilize_report_edges()` cross-faded the first and last 140–180 ms into a flat baseline; a beat 60 ms from the strip end printed at **14 %** of its true height. Filter transients are already prevented upstream by 0.5 s of real pre-roll plus reflect padding.
- **6×2 strips were also being cut.** Two noise-triggered trims and an unconditional 3 %-per-side "hard trim" discarded up to **16 %** of the recorded strip even on clean traces, and the drawing code faded both ends. All removed — 5000 samples in now means 5000 out.
- HRV and hyperkalemia report strips were already free of tapers and needed no change.

#### ✅ Live display (`src/ecg/hyperkalemia_test.py`, `src/ecg/hrv_test.py`)
- **Scrolling instead of raster sweep.** The HRV window's CRT-style eraser bar (80 samples plus a 14 px black pen) blanked part of the trace as it swept; the trace now scrolls with the newest sample pinned to the right edge.
- **Downsampling mode.** Both windows used `auto=True, mode='peak'`, which collapses each pixel column into a min/max pair and draws the trace as vertical bars — the background showed between them as black speckle in the line. Both now use the 12-lead's `ds=1, auto=False, mode='subsample'`.
- **Point density.** Hyperkalemia lanes are ~900 px wide, so plotting 6000 points meant 6.7 per pixel column and a hairy line. Now decimated 2× to 1.7 per column, matching the 12-lead. The signal is low-passed at 25 Hz, so an effective 250 Hz is ten times Nyquist — R-wave amplitude is preserved exactly.
- **Non-finite guard.** Both curves draw with `connect='finite'`, so a single NaN breaks the line. Hyperkalemia sanitises before `setData`; HRV holds the last good value rather than writing NaN into the sweep buffer, where `np.clip` leaves it as NaN and the step guard cannot catch it.
- **Baseline follower.** The hyperkalemia display anchor was measured once and locked forever, so drift pushed the trace off centre. It now uses the 12-lead's slow exponential follower (α = 0.0005) plus DC removal.
- **Filters.** AC 50 Hz / EMG 25 Hz / baseline 0.5 Hz are fixed for HRV and hyperkalemia on screen and in their reports; only the 12-lead follows the settings screen. The AC filter previously came from settings in ten places across the two report generators, half of them defaulting to `off` — so a report could print with no mains notch at all.
- **Trace style:** `#00FF00` at 2.0 px in both windows, matching the green the holter modules already use.

#### ✅ Performance — 8 GB / i3 minimum spec (`src/ecg/hyperkalemia_test.py`, `src/main.py`, `src/utils/license_manager.py`)
- **Buffer writes:** the capture loop called `np.roll` per sample per lead, copying a 10,000-element buffer 500 times a second for each of 7 leads, plus a Lead II buffer that is never read during capture — about 40 million element moves per second. Replaced with index-addressed rings: **74.8 ms → 1.9 ms** per second of capture (40× cheaper), roughly 18 % of a core returned on a minimum-spec machine.
- **Antialiasing** is switched off under `is_low_spec_mode()` (≤8 GB RAM or ≤4 threads), where it roughly triples line-drawing cost.
- **Login wait halved:** the licence heartbeat (~3.8 s) and the credential check (~3.8 s) ran sequentially on the UI thread. They are independent, so they now run concurrently — measured **8.48 s → 4.50 s**. The gate still fails closed if the worker stalls. The credential check also stops retrying the same identifier with the other password form after a seat-state answer, which cannot change the outcome.

#### ✅ UI
- Removed the **Ctrl + E** row from the History window shortcuts sheet (`src/dashboard/history_window.py`); the binding had already been removed with the email button, so the sheet advertised a shortcut that did nothing.

### 🔧 [2026-08-03] — Security, Report Formatting, 12-Lead Freeze/Resume & Dashboard Fixes

#### ✅ Security Hardening & Loophole Audit
- **Admin Panel Authentication (`src/dashboard/admin_reports.py`):** Strictly enforced custom environment passwords (`ADMIN_PASSWORD` / `CARDIOX_ADMIN_PASS`) in `_check_admin_credentials()` without hardcoded fallback bypasses.
- **Phone Number Validation (`src/ecg/hyperkalemia_ecg_report_generator.py`):** Updated `format_indian_phone()` to require a 10-digit count before adding `+91-`. Preserves raw input for invalid digit counts to prevent malformed numbers.
- **Division-by-Zero Protection (`src/ecg/hyperkalemia_ecg_report_generator.py`):** Added `speed_mm_per_s <= 0` guard to `beats_in_boxes()`.
- **Locale & Unit Parsing (`src/ecg/hyperkalemia_ecg_report_generator.py`):** Enhanced `_safe_float()` to handle comma decimal separators (`"72,5"`) and trailing unit strings (`"72 BPM"`).
- **Patient Data Privacy (`.gitignore`):** Added `ecg_history.json` to `.gitignore` to prevent local patient history records from being committed.

#### ✅ Hyperkalemia Report Generator Formatting Sync
- **Layout Alignment (`src/ecg/hyperkalemia_ecg_report_generator.py`):** Synchronized all Page 2 landscape coordinates with commit `0e0d8e1`:
  - Patient info X-offset: `13.85` → `11.85`. Adjusted Y positions for Name, Age, Gender, Report Type, Date/Time.
  - Organization contact block: X `590` → `579`, Y `545.90` → `546.40`.
  - Vital parameters: Left column HR/PR/QRS/RR/QT Y alignments; Right column QTc/QTCF/Est. K+ X/Y alignments.
  - Doctor signature footer: Shifted reference, doctor name, and signature lines down by 5-6 points and aligned X offsets.

#### ✅ 12-Lead ECG Freeze/Resume & Lead-Off Metric Fixes
- **Lead Off Reset (`src/ecg/twelve_lead_test.py`):** Corrected `reset_metrics_to_zero()` logic to check `_lead_off_latched`, ensuring metric labels (`heart_rate`, `pr_interval`, `qrs_duration`, `qtc_interval`) reset to 0 immediately when leads disconnect.
- **Resume Button Reset (`src/ecg/twelve_lead_test.py`):** Added an explicit lead-off check in `_resume_live_view()` so clicking **Resume** while leads are disconnected instantly resets top-bar metrics to `0 BPM` / `0 ms` / `--` and keeps the lead disconnection alert active.
- **Frozen Report Sanitization (`src/ecg/twelve_lead_test.py`):** Updated `_freeze_current_view()` to force `0` for all interval metrics when frozen during lead disconnection.
- **Fallback Elimination (`src/ecg/twelve_lead_test.py`):** Replaced default `60 BPM` and `160/148 ms PR` fallback values with `0` when fewer than 2 R-peaks are detected or when signal is flat.

#### ✅ Dashboard Sticky Metric Cache & Interpretation Fixes
- **Sticky Cache Invalidation (`src/dashboard/dashboard.py`):** Fixed `_dashboard_last_valid` cache that was retaining old PR values (e.g. `151 ms`) upon device reconnect or 0 BPM. Invalidated cached metrics whenever live HR is 0.
- **0 BPM Interpretation Guard (`src/dashboard/dashboard.py`):** Added `if hr <= 0:` guard in `update_ecg_interpretation()`. The dashboard interpretation box now displays *"Waiting for stable ECG data..."* when HR is 0 BPM instead of outputting false PR status or *"Normal Sinus Rhythm"*.

#### ✅ History Table Cleanup
- **Removed "Findings" Column (`src/dashboard/history_window.py`):** Column count reduced from 10 → 9; `"Findings"` removed from table headers and value list to eliminate horizontal scrolling. Findings text remains visible inside the in-app PDF preview panel.

#### ✅ Added: `tests/test_history_and_hyperkalemia.py` — 104 new unit tests
New test file covering 11 test suites:
- `TestFormatIndianPhone` — 13 edge cases (None, empty, prefixes, integers, Unicode-safe)
- `TestBeatsInBoxes` — 10 cases (ECG paper-speed math, zero guards, proportionality)
- `TestSafeFloat` — 11 cases (type coercion, unit strings, list input, defaults)
- `TestECGGridConstants` — 10 cases (A4 landscape dims, box sizes, sampling-rate guards)
- `TestHistoryRowValuesCount` — 10 cases (9-column assertion, Findings removal, fallbacks)
- `TestHistoryDateParsing` — 8 cases (malformed dates, partial dates, sort order)
- `TestHistorySearchFilter` — 8 cases (case-insensitive, Unicode, XSS-safe, list findings)
- `TestInferReportType` — 8 cases (filename-based inference, explicit override, case)
- `TestRiskSeverityClassifier` — 11 cases (critical/warning/normal keywords, list fields)
- `TestCircularBufferUnwrap` — 7 cases (ptr boundaries, NumPy arrays, length invariants)
- `TestFindingsSummaryTruncation` — 8 cases (60-char cap, ellipsis, empty list)

---

### 🔧 [2026-07-30] — Lead Disconnection & Signal Handling Fixes

#### ❌ Bug Fixed: V1–V6 chest leads showing garbage noise when RA (Right Arm) lead is disconnected

**Root Cause:** Chest leads (V1–V6) are measured against Wilson's Central Terminal (WCT = `(RA + LA + LL) / 3`). When RA or limb leads disconnect, WCT floats and breaks. However, because physical chest electrodes remain attached, the hardware returned `connected = True`, passing chaotic floating ADC noise to V1–V6 while limb leads were flatlined.

**Fix Applied (`src/ecg/serial/packet_parser.py`):**
- When limb source leads (`I`, `II`) are disconnected (`None`), the parser now explicitly invalidates all chest leads (`V1` through `V6` set to `None`).
- Replaced garbage noise waveforms on chest leads with clean flatlines and added them to the red "Leads Off" indicator, aligning PC behavior with the Android app.

#### ❌ Bug Fixed: HRV and Hyperkalemia tests holding stale metrics during lead disconnection

**Root Cause:** Unlike the 12-lead ECG view, the HRV and Hyperkalemia test modules did not automatically force calculated interval metrics (`HR`, `RR`, `PR`, `QRS`, `QT`, `QTc`) to zero when all patient leads were disconnected.

**Fix Applied (`src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
- Updated `update_metrics()` in both tests to check lead connection and signal variance (< 5.0 std-dev).
- When all leads disconnect: internal metric attributes reset to 0, smoothing buffers clear, and display labels show `0 BPM` / `0 ms`.
- Added `"No ECG signal detected. Check patient leads."` warning label in bold red placed to the left of the status indicator in top header bar (matching 12-lead screen).
- Maintained raw data buffering so canvas flatline visual representation remains intact.

---

### 🔧 [2026-07-29] — BPM Accuracy & Stability Fixes

#### ❌ Bug Fixed: HRV & Hyperkalemia showing wrong BPM on display and PDF report

**Root Cause:** `HolterBPMController` (a Holter-optimized 30-second window algorithm) was being used as the **primary BPM source** for both the live display label and `hyper_metric.json` / report generation. This caused the display to show values like `151 BPM` while the terminal (using the correct ECG algorithm) showed `83–85 BPM`.

**Fix Applied (`src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
- `_refresh_holter_bpm_label()` is now a **no-op** for HR display — it no longer overwrites the correct ECG-derived BPM every 2 seconds.
- `update_metrics()` now uses `calculate_ecg_metrics()` → `calculate_hr_rr()` (Pan-Tompkins R-peak detection → median RR → BPM) as the **primary source** — same algorithm used by the 12-lead ECG display.
- `HolterBPMController` is retained for **arrhythmia detection only**, used as a last-resort BPM fallback when `calculate_ecg_metrics()` returns 0 (signal too short).
- `self.last_heart_rate` is now synced from `calculate_ecg_metrics()`, so `hyper_metric.json` and PDF reports match the display.

#### ❌ Bug Fixed: BPM jumps to ~260 BPM for first few seconds on capture start

**Root Cause:** The ECG data buffer is initialized with flat `2048` ADC values. When real ECG samples first roll in, the sharp flat→signal transition creates fake R-peaks with RR intervals ~230ms → **260 BPM**. The startup filter only rejected too-slow RR intervals (> 6500ms), not too-fast ones.

**Fix Applied (`src/ecg/ecg_calculations.py`, `src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
- `calculate_hr_rr()` startup filter now rejects **both** too-long (< 10 BPM) AND too-short (> 200 BPM) RR intervals during initialization.
- `_STARTUP_LOCKOUT_BEATS` increased from `5` → `12` to cover more of the initialization transient.
- `update_metrics()` minimum wait increased from **0.5 seconds** → **3.0 seconds** of captured data before first BPM calculation, ensuring the flat buffer region has fully rolled out.

#### ❌ Bug Fixed: `datetime` AttributeError causing application startup crash

**Root Cause:** Multiple methods in `dashboard.py` had local `from datetime import datetime` imports inside function bodies, shadowing the module-level `import datetime`. This caused `AttributeError: type object 'datetime.datetime' has no attribute 'datetime'` on startup.

**Fix Applied (`src/dashboard/dashboard.py`):**
- Removed all method-level `from datetime import datetime` imports.
- All time calls now use the top-level `import datetime` → `datetime.datetime.now()`.
- Added `hasattr(self, 'metric_labels')` guard in `animate_heartbeat()` to prevent startup race condition.

