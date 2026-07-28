# CardioX — Web HCP Clinical Portal & 12-Lead Real-Time Telemetry System

![CardioX Web Portal Header](https://img.shields.io/badge/CardioX-Web%20HCP%20Portal-0284c7?style=for-the-badge&logo=heart)
![Web Serial API](https://img.shields.io/badge/Hardware-Web%20Serial%20API-10b981?style=for-the-badge)
![HTML5 Canvas](https://img.shields.io/badge/Renderer-60%20FPS%20Canvas-f59e0b?style=for-the-badge)
![PDF Generator](https://img.shields.io/badge/Reports-A4%20Clinical%20PDF-ef4444?style=for-the-badge)

The **CardioX Web HCP Clinical Portal** is a web application designed for real-time 12-lead ECG monitoring, telemetry metrics, and diagnostic report generation. Built using Vanilla HTML5 Canvas, modern Web Serial API, and Medical-Grade DSP Filter Chains, it connects directly to CardioX ECG hardware over USB (`COM8` @ 500 SPS) without requiring third-party plugins.

---

## 🌟 Key Features

### 1. Direct USB Hardware Streaming (Web Serial API)
* Native **Web Serial API** reader communicating directly with CardioX hardware on `COM8` (115200 baud, 500 samples/second).
* Implements the full **22-byte hardware protocol** (`0xE8` start byte, `0x8E` end byte, 12-bit ADC parsing).
* Transmits the **OpCode `0x10` START packet** automatically upon connection to initiate device stream.

### 2. 12-Lead Parallel Stack & Medical Grid Renderer
* **60 FPS HTML5 Canvas** rendering engine supporting **12x1 Parallel Stack**, **6x2 Standard**, and **3x4 Grid** layouts.
* **Vertical Scrollbar Support**: Expands to $2,400\text{px}$ canvas height ($200\text{px}$ per lead row) for spacious vertical separation between leads without waveform overlapping.
* **$1\text{ mV} \times 0.2\text{ s}$ Calibration Pulses**: Renders standard clinical calibration marks at the onset of every lead channel.

### 3. Standard Clinical Display Window
* Default **5.0-second display window** ($240\text{ px/sec}$) providing clear, un-crowded P-Q-R-S-T wave resolution.
* Includes interactive **Window Selector** (`2.5s Zoom`, `5.0s Std Monitor`, `10.0s Full`).

### 4. Medical-Grade DSP Filter Chain
* Built-in 3-stage IIR DSP Filter Chain matching CardioX `ecg_filters.py`:
  1. **0.5 Hz Highpass Filter**: Baseline wander removal.
  2. **50 Hz AC Notch Filter**: Powerline noise elimination.
  3. **35 Hz Lowpass Filter**: EMG muscle noise filtering.

### 5. Live Dynamic Clinical Telemetry Metrics
Calculates and updates core clinical telemetry metrics in real time every 500ms:
* **`HR`** — Heart Rate (BPM) via Pan-Tompkins R-peak detection & EMA smoothing.
* **`PR`** — P-R Interval (ms).
* **`QRS`** — QRS Complex Duration (ms).
* **`QT / QTc`** — QT Interval & **Bazett Correction Formula** ($\text{QTc} = \frac{\text{QT}}{\sqrt{\text{RR}_{\text{sec}}}}$).

### 6. A4 Diagnostic ECG PDF Report Generator
* **One-Click PDF Export**: Generates an A4 Diagnostic PDF Clinical Report matching the exact structure and layout of CardioX desktop software (`ecg_report_generator.py`).
* Includes patient demographics, 3-column telemetry box, high-res 12-lead waveform canvas capture, AI rhythm interpretations, and attending physician electronic sign-off.

---

## 📁 Repository Structure

```
web_hcp_portal/
├── index.html       # HTML5 structure, clinical controls toolbar, & Doctor's panel
├── styles.css       # Clinical dark slate & light themes, custom scrollbars, layout grid
├── app.js           # 60 FPS Canvas renderer, Web Serial parser, DSP filters, PDF generator
└── README.md        # Comprehensive technical documentation & usage guide
```

---

## 🚀 Quick Start Guide

### 1. Launch Local Web Server
Run Python's built-in HTTP server inside the project root:
```bash
python -m http.server 8000 --directory web_hcp_portal
```

### 2. Open in Browser
Open Google Chrome or Microsoft Edge and navigate to:
```
http://localhost:8000
```

### 3. Connect to ECG Hardware
1. Ensure no other application (e.g. `main.py`) is locking `COM8`.
2. Click **`Connect COM8 (Web Serial USB)`**.
3. Select **`COM8`** in the Chrome native device selector and click **Connect**.
4. To test without hardware, toggle **`Hardware Simulator: ON`**.

---

## 📄 License & Attribution
Developed for **Deck Mount Electronics Pvt. Ltd.** / **CardioX Team**.
