# 📜 CardioX - Change Log

All notable changes, bug fixes, and feature updates to the CardioX platform are documented in this file.

---

## 🔧 [1.1.0] — 2026-07-30

### ❌ Bug Fixed: V1–V6 chest leads showing garbage noise when RA (Right Arm) lead is disconnected

- **Root Cause:** Chest leads (V1–V6) are measured against Wilson's Central Terminal (WCT = `(RA + LA + LL) / 3`). When RA or limb leads disconnect, WCT floats and breaks. However, because physical chest electrodes remain attached to the patient body, the hardware returned `connected = True`, passing chaotic floating ADC noise to V1–V6 while limb leads were flatlined.
- **Fix Applied (`src/ecg/serial/packet_parser.py`):**
  - When limb source leads (`I`, `II`) are disconnected (`None`), the parser now explicitly invalidates all chest leads (`V1` through `V6` set to `None`).
  - Replaced garbage noise waveforms on chest leads with clean flatlines and added them to the red "Leads Off" indicator, aligning PC software behavior with the Android app.

---

### ❌ Bug Fixed: HRV and Hyperkalemia tests holding stale metrics during lead disconnection

- **Root Cause:** Unlike the 12-lead ECG view, the HRV and Hyperkalemia test modules did not automatically force calculated interval metrics (`HR`, `RR`, `PR`, `QRS`, `QT`, `QTc`) to zero when all patient leads were disconnected.
- **Fix Applied (`src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
  - Updated `update_metrics()` in both tests to check lead connection and signal variance (< 5.0 std-dev).
  - When all leads disconnect: internal metric attributes reset to 0, smoothing buffers clear, and display labels show `0 BPM` / `0 ms`.
  - Added `"No ECG signal detected. Check patient leads."` warning label in bold red placed to the left of the status indicator in top header bar (matching 12-lead screen).
  - Maintained raw data buffering so canvas flatline visual representation remains intact.

---

## 🔧 [1.0.9] — 2026-07-29

### ❌ Bug Fixed: HRV & Hyperkalemia showing wrong BPM on display and PDF report

- **Root Cause:** `HolterBPMController` (a Holter-optimized 30-second window algorithm) was being used as the primary BPM source for both live display label and report generation. This caused the display to show values like `151 BPM` while the terminal (using correct ECG algorithm) showed `83–85 BPM`.
- **Fix Applied (`src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
  - `_refresh_holter_bpm_label()` is now a no-op for HR display — it no longer overwrites the correct ECG-derived BPM every 2 seconds.
  - `update_metrics()` now uses `calculate_ecg_metrics()` → `calculate_hr_rr()` (Pan-Tompkins R-peak detection → median RR → BPM) as the primary source — same algorithm used by the 12-lead ECG display.
  - `HolterBPMController` is retained for arrhythmia detection only, used as a last-resort BPM fallback when `calculate_ecg_metrics()` returns 0 (signal too short).
  - `self.last_heart_rate` is now synced from `calculate_ecg_metrics()`, so `hyper_metric.json` and PDF reports match the display.

---

### ❌ Bug Fixed: BPM jumps to ~260 BPM for first few seconds on capture start

- **Root Cause:** The ECG data buffer is initialized with flat `2048` ADC values. When real ECG samples first roll in, the sharp flat→signal transition creates fake R-peaks with RR intervals ~230ms → **260 BPM**. The startup filter only rejected too-slow RR intervals (> 6500ms), not too-fast ones.
- **Fix Applied (`src/ecg/ecg_calculations.py`, `src/ecg/hrv_test.py`, `src/ecg/hyperkalemia_test.py`):**
  - `calculate_hr_rr()` startup filter now rejects **both** too-long (< 10 BPM) AND too-short (> 200 BPM) RR intervals during initialization.
  - `_STARTUP_LOCKOUT_BEATS` increased from `5` → `12` to cover more of the initialization transient.
  - `update_metrics()` minimum wait increased from 0.5s → 3.0s of captured data before first BPM calculation, ensuring the flat buffer region has fully rolled out.

---

### ❌ Bug Fixed: `datetime` AttributeError causing application startup crash

- **Root Cause:** Multiple methods in `dashboard.py` had local `from datetime import datetime` imports inside function bodies, shadowing module-level `import datetime`.
- **Fix Applied (`src/dashboard/dashboard.py`):**
  - Removed all method-level `from datetime import datetime` imports.
  - All time calls now use top-level `import datetime` → `datetime.datetime.now()`.
  - Added `hasattr(self, 'metric_labels')` guard in `animate_heartbeat()` to prevent startup race condition.
