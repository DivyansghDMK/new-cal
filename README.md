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
**Status:** 🟢 Production Ready | **Last Updated:** July 2026
