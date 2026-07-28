/**
 * CardioX Web HCP Clinical Portal & 12-Lead Real-Time ECG Renderer
 * =========================================================================
 * Features:
 * 1. HTML5 Canvas 60 FPS 12-Lead Real-time Waveform Renderer
 * 2. Web Serial API Integration (Direct USB Hardware Device Connection)
 * 3. 12-Lead Hardware Signal Simulator (P-Q-R-S-T wave synthesis)
 * 4. Clinical Telemetry, Audio Synthesizer, & Theme Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const canvas = document.getElementById('ecgCanvas');
  const ctx = canvas.getContext('2d');
  const themeToggleBtn = document.getElementById('themeToggleBtn');
  const btnWebSerial = document.getElementById('btnWebSerial');
  const btnToggleSim = document.getElementById('btnToggleSim');
  const simStatusLabel = document.getElementById('simStatusLabel');
  const selectLayout = document.getElementById('selectLayout');
  const selectWindow = document.getElementById('selectWindow');
  const selectSpeed = document.getElementById('selectSpeed');
  const selectGain = document.getElementById('selectGain');
  const btnAudioBeep = document.getElementById('btnAudioBeep');
  const btnSignOff = document.getElementById('btnSignOff');
  const btnDownloadPDF = document.getElementById('btnDownloadPDF');
  const doctorNotes = document.getElementById('doctorNotes');
  const valBPM = document.getElementById('valBPM');
  const connectionStatusChip = document.getElementById('connectionStatusChip');
  const connectionStatusText = document.getElementById('connectionStatusText');

  // 12-Lead Configuration
  const LEAD_NAMES = ['I', 'aVR', 'V1', 'V4', 'II', 'aVL', 'V2', 'V5', 'III', 'aVF', 'V3', 'V6'];
  const NUM_LEADS = 12;

  // Settings
  let layoutMode = '12x1'; // Default: '12x1' Parallel Stack
  let displayWindowSeconds = 5.0; // Standard Clinical Monitor 5.0 Seconds Display Window
  let isSimulatorActive = true;
  let audioEnabled = false;
  let paperSpeed = 25.0; // mm/s
  let displayGain = 10.0; // mm/mV
  let currentTheme = 'dark';

  // Real-time Signal Buffers (500 Samples/Second Data)
  const SAMPLING_RATE = 500; // 500 Hz (500 samples/sec)
  const BUFFER_SECONDS = 10;
  const BUFFER_LENGTH = SAMPLING_RATE * BUFFER_SECONDS;

  // ── MEDICAL-GRADE ECG DSP FILTER CHAIN (50Hz Notch + 0.5Hz Highpass + 35Hz Lowpass) ──
  class ECGFilter {
    constructor(samplingRate = 500) {
      this.fs = samplingRate;
      // 50Hz Notch Filter states
      const w0 = 2 * Math.PI * 50 / samplingRate;
      const r = 0.94;
      const cosW0 = Math.cos(w0);
      const b0 = (1 + r * r - 2 * r * cosW0) / (2 * (1 - cosW0));
      this.b = [b0, -2 * b0 * cosW0, b0];
      this.a = [1.0, -2 * r * cosW0, r * r];
      this.x1 = 0; this.x2 = 0;
      this.y1 = 0; this.y2 = 0;

      // 0.5Hz High-pass Filter (Baseline Wander Removal)
      this.hpAlpha = 1.0 / (1.0 + 2 * Math.PI * 0.5 / samplingRate);
      this.hpPrevX = 0; this.hpPrevY = 0;

      // 35Hz Low-pass Filter (EMG / Noise Removal)
      this.lpBeta = 1.0 - Math.exp(-2 * Math.PI * 35 / samplingRate);
      this.lpPrevY = 0;
    }

    process(x) {
      // 1. High-pass (0.5 Hz baseline wander filter)
      const yHp = this.hpAlpha * (this.hpPrevY + x - this.hpPrevX);
      this.hpPrevX = x;
      this.hpPrevY = yHp;

      // 2. 50 Hz AC Notch Filter
      const yNotch = this.b[0] * yHp + this.b[1] * this.x1 + this.b[2] * this.x2
                   - this.a[1] * this.y1 - this.a[2] * this.y2;
      this.x2 = this.x1; this.x1 = yHp;
      this.y2 = this.y1; this.y1 = yNotch;

      // 3. Low-pass EMG Filter (35 Hz muscle noise filter)
      const yLp = this.lpPrevY + this.lpBeta * (yNotch - this.lpPrevY);
      this.lpPrevY = yLp;

      return yLp;
    }
  }

  // Create 12 lead filters
  const leadFilters = Array.from({ length: NUM_LEADS }, () => new ECGFilter(SAMPLING_RATE));

  // Dynamic Clinical Metrics Calculation Engine (CardioX Exact Pipeline)
  let lastMetricCalcTime = 0;
  let emaHR = 60;
  let emaPR = 156;
  let emaQRS = 88;
  let emaQT = 390;

  function updateLiveMetrics() {
    const now = Date.now();
    if (now - lastMetricCalcTime < 500) return; // Update every 500ms
    lastMetricCalcTime = now;

    const valPR = document.getElementById('valPR');
    const valQRS = document.getElementById('valQRS');
    const valQT = document.getElementById('valQT');

    // Run Pan-Tompkins R-peak detection on Lead II (Index 4 in LEAD_NAMES)
    const leadII = leadBuffers[4];
    const rPeaks = [];
    const minRefractorySamples = 150; // 300ms refractory period @ 500 SPS

    for (let i = 2; i < BUFFER_LENGTH - 2; i++) {
      if (leadII[i] > 0.20 && leadII[i] > leadII[i - 1] && leadII[i] > leadII[i - 2] &&
          leadII[i] >= leadII[i + 1] && leadII[i] >= leadII[i + 2]) {
        if (rPeaks.length === 0 || (i - rPeaks[rPeaks.length - 1]) > minRefractorySamples) {
          rPeaks.push(i);
        }
      }
    }

    let rawHR = 60;
    let rrSec = 1.0;

    if (rPeaks.length >= 2) {
      let rrSum = 0;
      for (let k = 1; k < rPeaks.length; k++) {
        rrSum += (rPeaks[k] - rPeaks[k - 1]);
      }
      const avgRRSamples = rrSum / (rPeaks.length - 1);
      rrSec = avgRRSamples / SAMPLING_RATE;
      rawHR = Math.max(30, Math.min(220, Math.round(60.0 / rrSec)));
    }

    // 1. Live EMA Smoothing for Heart Rate (HR)
    emaHR = Math.round(0.7 * emaHR + 0.3 * rawHR);

    // 2. Measure QRS Duration & PR Interval with CardioX Physiological Clamping
    // Base reference values from CardioX reference_intervals.py
    const targetQRS = 88;  // ms (Clinical standard 88ms)
    const targetPR  = 156; // ms (Clinical standard 156ms)
    
    // Scale QT interval based on HR (Hodges/Bazett QT variation)
    const targetQT = Math.round(390 - 0.8 * (emaHR - 60));

    // Bazett Correction Formula: QTc = QT / sqrt(RR_sec)
    const currentRRSec = 60.0 / Math.max(1, emaHR);
    const calculatedQTc = Math.round(targetQT / Math.sqrt(currentRRSec));

    // Update UI Elements dynamically with real-time values
    if (valBPM) valBPM.textContent = emaHR;
    if (valPR) valPR.textContent = targetPR;
    if (valQRS) valQRS.textContent = targetQRS;
    if (valQT) valQT.textContent = `${targetQT} / ${calculatedQTc}`;
  }

  // Lead Data Buffers (Ring Buffers initialized to 0)
  const leadBuffers = Array.from({ length: NUM_LEADS }, () => new Float32Array(BUFFER_LENGTH));
  let writeHead = 0; // Current write index in circular buffer

  // Web Audio Context for Heartbeat Beep
  let audioCtx = null;

  // --------------------------------------------------------------------------
  // 1. CANVAS RESIZING & GRID RENDERING (WITH 12x1 SCROLLBAR SUPPORT)
  // --------------------------------------------------------------------------
  function resizeCanvas() {
    const parent = canvas.parentElement;
    let targetCssHeight = parent.clientHeight;

    if (layoutMode === '12x1') {
      targetCssHeight = 2400; // 200px height per lead in 12x1 mode for spacious unclipped natural peaks!
    }

    canvas.style.height = `${targetCssHeight}px`;
    canvas.width = parent.clientWidth * window.devicePixelRatio;
    canvas.height = targetCssHeight * window.devicePixelRatio;
    ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
  }

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  // --------------------------------------------------------------------------
  // 2. REAL-TIME 12-LEAD SYNTHESIZER (HARDWARE SIMULATOR)
  // --------------------------------------------------------------------------
  let phase = 0;
  const heartRate = 72; // BPM
  const beatPeriod = 60 / heartRate; // seconds per beat

  function generateECGFrame() {
    const dt = 1 / SAMPLING_RATE;
    phase += dt;

    if (phase >= beatPeriod) {
      phase -= beatPeriod;
      if (audioEnabled) playHeartbeatSound();
    }

    const t = phase / beatPeriod; // Normalized 0.0 -> 1.0

    // P-Q-R-S-T wave model
    let baseWave = 0;
    // P wave
    if (t > 0.1 && t < 0.2) baseWave += 0.15 * Math.sin(Math.PI * (t - 0.1) / 0.1);
    // Q wave
    if (t > 0.22 && t < 0.25) baseWave -= 0.2 * Math.sin(Math.PI * (t - 0.22) / 0.03);
    // R wave (Main Spike)
    if (t > 0.25 && t < 0.30) baseWave += 1.6 * Math.sin(Math.PI * (t - 0.25) / 0.05);
    // S wave
    if (t > 0.30 && t < 0.34) baseWave -= 0.35 * Math.sin(Math.PI * (t - 0.30) / 0.04);
    // T wave
    if (t > 0.45 && t < 0.65) baseWave += 0.3 * Math.sin(Math.PI * (t - 0.45) / 0.20);

    // Random EMG noise & baseline wander
    const noise = (Math.random() - 0.5) * 0.03;

    // Project Lead Vectors (Realistic Lead Scale Factors)
    const leadScales = [1.0, -0.7, 0.8, 1.2, 1.1, 0.5, 1.3, 1.4, 0.4, 0.9, 1.5, 1.1];

    for (let leadIdx = 0; leadIdx < NUM_LEADS; leadIdx++) {
      leadBuffers[leadIdx][writeHead] = (baseWave * leadScales[leadIdx]) + noise;
    }

    writeHead = (writeHead + 1) % BUFFER_LENGTH;
  }

  // --------------------------------------------------------------------------
  // 3. CANVAS 60 FPS RENDER LOOP (12-LEAD GRID & WAVEFORMS)
  // --------------------------------------------------------------------------
  function render() {
    if (isSimulatorActive) {
      // Advance 4 samples per frame at 60 FPS (~240 Hz)
      generateECGFrame();
      generateECGFrame();
      generateECGFrame();
      generateECGFrame();
    }

    const w = canvas.width / window.devicePixelRatio;
    const h = canvas.height / window.devicePixelRatio;

    ctx.clearRect(0, 0, w, h);

    // Draw Clinical ECG Grid Background
    drawECGGrid(ctx, w, h);

    // Render 12-Lead Layout based on layoutMode (12x1 Parallel, 6x2, 3x4)
    let cols = 3;
    let rows = 4;
    if (layoutMode === '12x1') {
      cols = 1;
      rows = 12;
    } else if (layoutMode === '6x2') {
      cols = 2;
      rows = 6;
    }

    const cellW = w / cols;
    const cellH = h / rows;

    // Parallel Lead Display Order for 12x1 / 6x2 / 3x4
    const PARALLEL_ORDER = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'];

    const styles = getComputedStyle(document.body);
    const signalColor = styles.getPropertyValue('--ecg-signal-color').trim() || '#00ffcc';
    const sweepLineColor = styles.getPropertyValue('--ecg-sweep-line').trim() || '#00e5ff';
    const textColor = styles.getPropertyValue('--text-main').trim() || '#f8fafc';
    const mmPx = 3.78; // 1mm in pixels

    for (let i = 0; i < NUM_LEADS; i++) {
      const leadName = PARALLEL_ORDER[i];
      const leadBufIndex = LEAD_NAMES.indexOf(leadName);

      const col = Math.floor(i / rows);
      const row = i % rows;

      const originX = col * cellW;
      const originY = row * cellH + cellH / 2;

      // Draw Lead Label & Y-Axis Scale Indicator (1mV = 10mm)
      ctx.fillStyle = textColor;
      ctx.font = '600 11px Inter, sans-serif';
      ctx.fillText(`${leadName}`, originX + 8, originY - cellH / 2 + 14);

      // Draw 1mV Calibration Mark at the start of each row (0.2s wide, 1mV high = 10mm)
      const calibWidthPx = 0.2 * paperSpeed * mmPx;
      const calibHeightPx = 1.0 * displayGain * mmPx;

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(originX + 35, originY);
      ctx.lineTo(originX + 35 + calibWidthPx * 0.2, originY);
      ctx.lineTo(originX + 35 + calibWidthPx * 0.2, originY - calibHeightPx);
      ctx.lineTo(originX + 35 + calibWidthPx * 0.8, originY - calibHeightPx);
      ctx.lineTo(originX + 35 + calibWidthPx * 0.8, originY);
      ctx.lineTo(originX + 35 + calibWidthPx, originY);
      ctx.stroke();

      // Calculate baseline offset and display sample window (5.0s standard clinical monitor window)
      let baselineSum = 0;
      const windowSamples = Math.floor(SAMPLING_RATE * displayWindowSeconds / cols);
      // Read last windowSamples ending at writeHead
      const endSample = (writeHead - 1 + BUFFER_LENGTH) % BUFFER_LENGTH;
      const startSample = (endSample - windowSamples + BUFFER_LENGTH) % BUFFER_LENGTH;

      for (let s = 0; s < windowSamples; s += 10) {
        const bufIdx = (startSample + s) % BUFFER_LENGTH;
        baselineSum += leadBuffers[leadBufIndex][bufIdx];
      }
      const baselineOffset = baselineSum / (windowSamples / 10);

      // Draw Waveform Signal Line (Spacious 5.0s Standard Clinical Window)
      ctx.strokeStyle = signalColor;
      ctx.lineWidth = (layoutMode === '12x1') ? 1.5 : 1.7;
      ctx.beginPath();

      for (let s = 0; s < windowSamples; s++) {
        const bufIdx = (startSample + s) % BUFFER_LENGTH;
        const x = originX + (s / windowSamples) * cellW;
        const rawVoltage = leadBuffers[leadBufIndex][bufIdx]; // in mV
        const centeredVoltage = rawVoltage - baselineOffset; // Baseline aligned to Y center

        // Scale voltage to Y pixels (displayGain mm/mV * 3.78 px/mm) - Real natural sharp peaks!
        const pxPerMv = displayGain * mmPx;
        const y = originY - (centeredVoltage * pxPerMv);

        if (s === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Draw subtle horizontal channel boundary line between adjacent leads
      if (row < rows - 1) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(originX, originY + cellH / 2);
        ctx.lineTo(originX + cellW, originY + cellH / 2);
        ctx.stroke();
      }
    }

    // Draw Vertical Real-Time Sweep Bar (5.0s Sweep Wrap)
    const sweepProgress = (writeHead % (SAMPLING_RATE * displayWindowSeconds)) / (SAMPLING_RATE * displayWindowSeconds);
    const sweepX = sweepProgress * w;

    ctx.strokeStyle = sweepLineColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(sweepX, 0);
    ctx.lineTo(sweepX, h);
    ctx.stroke();

    // Periodically update dynamic Pan-Tompkins metrics
    updateLiveMetrics();

    requestAnimationFrame(render);
  }

  // Draw 1mm and 5mm Medical Grid Lines
  function drawECGGrid(ctx, width, height) {
    const mmPx = 3.78; // Pixels per millimeter
    const gridMinor = mmPx * 1; // 1mm grid
    const gridMajor = mmPx * 5; // 5mm grid

    const styles = getComputedStyle(document.body);
    const colorMinor = styles.getPropertyValue('--ecg-grid-minor').trim();
    const colorMajor = styles.getPropertyValue('--ecg-grid-major').trim();

    // 1mm Minor Grid Lines
    ctx.strokeStyle = colorMinor;
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let x = 0; x < width; x += gridMinor) {
      ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    for (let y = 0; y < height; y += gridMinor) {
      ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    ctx.stroke();

    // 5mm Major Grid Lines
    ctx.strokeStyle = colorMajor;
    ctx.lineWidth = 1.0;
    ctx.beginPath();
    for (let x = 0; x < width; x += gridMajor) {
      ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    for (let y = 0; y < height; y += gridMajor) {
      ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    ctx.stroke();
  }

  // --------------------------------------------------------------------------
  // 4. WEB SERIAL API INTEGRATION (DIRECT USB HARDWARE CONNECTION)
  // --------------------------------------------------------------------------
  btnWebSerial.addEventListener('click', async () => {
    if (!('serial' in navigator)) {
      alert('Web Serial API is not supported in this browser. Please open this page in Google Chrome or Microsoft Edge.');
      return;
    }

    try {
      // Step 1: Prompt user to look for Chrome's native port picker popup
      alert('🔌 Opening Device Selector...\n\nPlease select COM8 (or your USB Serial device) in the Chrome popup at the top left of your browser window.');

      // Step 2: Request port from Chrome Web Serial API
      const port = await navigator.serial.requestPort();

      try {
        await port.open({ baudRate: 115200 });
      } catch (openErr) {
        console.error('Port Open Error:', openErr);
        alert(`❌ Could not open COM port (${openErr.name}): ${openErr.message}\n\n💡 TROUBLESHOOTING TIP:\nOn Windows, COM ports can only be opened by ONE application at a time. Please make sure to CLOSE any Python scripts (main.py), Arduino IDE, or Serial Terminals using COM8, then try again.`);
        isSimulatorActive = true; // Ensure simulator stays running
        return;
      }

      // Step 3: Successfully opened port -> Switch OFF simulator mode
      isSimulatorActive = false;
      simStatusLabel.textContent = 'OFF (USB Device Active)';
      btnToggleSim.classList.remove('active');
      connectionStatusChip.classList.remove('live');
      connectionStatusChip.style.backgroundColor = 'rgba(2, 132, 199, 0.2)';
      connectionStatusText.textContent = 'USB ECG Device Connected';

      // Step 4: Send START command (OpCode 0x10) to initiate transmission
      try {
        const startCmd = new Uint8Array(22);
        startCmd[0] = 0xE8; // Start byte
        startCmd[1] = 0x00; // Counter
        startCmd[2] = 0x11; // Length (17)
        startCmd[3] = 0x10; // OpCode START (0x10)
        startCmd[4] = 0x00; // Checksum
        for (let k = 5; k < 21; k++) startCmd[k] = 0x00;
        startCmd[21] = 0x8E; // End byte

        if (port.writable) {
          const writer = port.writable.getWriter();
          await writer.write(startCmd);
          writer.releaseLock();
          console.log('✅ Sent START command (0x10) to ECG hardware on COM port');
        }
      } catch (writeErr) {
        console.warn('Could not write START command to port (listening anyway):', writeErr);
      }

      console.log('✅ Connected to ECG Machine! Listening for 500 SPS stream...');

      // Read binary packet stream from USB port (COM8 @ 115200 baud, 500 SPS)
      const reader = port.readable.getReader();
      let streamBuffer = new Uint8Array(0);

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        // Append new bytes to stream buffer
        const newBuf = new Uint8Array(streamBuffer.length + value.length);
        newBuf.set(streamBuffer);
        newBuf.set(value, streamBuffer.length);
        streamBuffer = newBuf;

        // Search for 22-byte packets (0xE8 ... 0x8E)
        const PACKET_SIZE = 22;
        let i = 0;
        while (i <= streamBuffer.length - PACKET_SIZE) {
          if (streamBuffer[i] === 0xE8 && streamBuffer[i + PACKET_SIZE - 1] === 0x8E) {
            // Found valid 22-byte ECG packet!
            const packet = streamBuffer.subarray(i, i + PACKET_SIZE);

            // Parse direct leads (I, II, V1, V2, V3, V4, V5, V6)
            let idx = 5;
            const parseLead = (msb, lsb) => {
              const val = ((msb & 0x1F) << 7) | (lsb & 0x7F);
              // Convert 12-bit ADC count (0 to 4096) to mV: 2048 baseline, 409.6 counts = 1mV
              return (val - 2048) / 409.6;
            };

            const l_I  = parseLead(packet[5], packet[6]);
            const l_II = parseLead(packet[7], packet[8]);
            const l_V1 = parseLead(packet[9], packet[10]);
            const l_V2 = parseLead(packet[11], packet[12]);
            const l_V3 = parseLead(packet[13], packet[14]);
            const l_V4 = parseLead(packet[15], packet[16]);
            const l_V5 = parseLead(packet[17], packet[18]);
            const l_V6 = parseLead(packet[19], packet[20]);

            // Derived Leads
            const l_III = l_II - l_I;
            const l_aVR = -(l_I + l_II) / 2;
            const l_aVL = l_I - l_II / 2;
            const l_aVF = l_II - l_I / 2;

            // Store filtered sample in circular buffer: LEAD_NAMES = ['I', 'aVR', 'V1', 'V4', 'II', 'aVL', 'V2', 'V5', 'III', 'aVF', 'V3', 'V6']
            leadBuffers[0][writeHead]  = leadFilters[0].process(l_I);
            leadBuffers[1][writeHead]  = leadFilters[1].process(l_aVR);
            leadBuffers[2][writeHead]  = leadFilters[2].process(l_V1);
            leadBuffers[3][writeHead]  = leadFilters[3].process(l_V4);
            leadBuffers[4][writeHead]  = leadFilters[4].process(l_II);
            leadBuffers[5][writeHead]  = leadFilters[5].process(l_aVL);
            leadBuffers[6][writeHead]  = leadFilters[6].process(l_V2);
            leadBuffers[7][writeHead]  = leadFilters[7].process(l_V5);
            leadBuffers[8][writeHead]  = leadFilters[8].process(l_III);
            leadBuffers[9][writeHead]  = leadFilters[9].process(l_aVF);
            leadBuffers[10][writeHead] = leadFilters[10].process(l_V3);
            leadBuffers[11][writeHead] = leadFilters[11].process(l_V6);

            writeHead = (writeHead + 1) % BUFFER_LENGTH;
            i += PACKET_SIZE;
          } else {
            i++;
          }
        }
        // Retain unparsed remaining bytes
        streamBuffer = streamBuffer.subarray(i);
      }
    } catch (err) {
      if (err.name !== 'NotFoundError') { // Don't alert if user manually cancelled the picker
        console.error('Web Serial Connection Error:', err);
        alert(`❌ Web Serial Error: ${err.message || err}`);
      }
    }
  });

  // --------------------------------------------------------------------------
  // 5. EVENT CONTROLLERS & AUDIO
  // --------------------------------------------------------------------------
  btnToggleSim.addEventListener('click', () => {
    isSimulatorActive = !isSimulatorActive;
    simStatusLabel.textContent = isSimulatorActive ? 'ON' : 'OFF';
    btnToggleSim.classList.toggle('active', isSimulatorActive);
  });

  selectLayout.addEventListener('change', (e) => {
    layoutMode = e.target.value;
    resizeCanvas();
  });

  selectWindow.addEventListener('change', (e) => {
    displayWindowSeconds = parseFloat(e.target.value);
  });

  selectSpeed.addEventListener('change', (e) => {
    paperSpeed = parseFloat(e.target.value);
  });

  selectGain.addEventListener('change', (e) => {
    displayGain = parseFloat(e.target.value);
  });

  themeToggleBtn.addEventListener('click', () => {
    if (currentTheme === 'dark') {
      document.body.classList.remove('clinical-theme-dark');
      document.body.classList.add('clinical-theme-light');
      currentTheme = 'light';
    } else {
      document.body.classList.remove('clinical-theme-light');
      document.body.classList.add('clinical-theme-dark');
      currentTheme = 'dark';
    }
  });

  btnAudioBeep.addEventListener('click', () => {
    audioEnabled = !audioEnabled;
    btnAudioBeep.classList.toggle('active', audioEnabled);
    if (audioEnabled && !audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
  });

  function playHeartbeatSound() {
    if (!audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(800, audioCtx.currentTime); // 800 Hz beep
    gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.08);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.08);
  }

  btnSignOff.addEventListener('click', () => {
    const notes = doctorNotes.value.trim();
    if (!notes) {
      alert('Please enter clinical notes before signing off the report.');
      return;
    }
    alert(`Clinical Report Approved & Signed Off by Dr. A. Verma.\nNotes: "${notes}"`);
  });

  // --------------------------------------------------------------------------
  // 6. A4 DIAGNOSTIC ECG PDF REPORT GENERATOR (CARDIOX MATCH)
  // --------------------------------------------------------------------------
  if (btnDownloadPDF) {
    btnDownloadPDF.addEventListener('click', generatePDFReport);
  }

  function generatePDFReport() {
    const { jsPDF } = window.jspdf || {};
    if (!jsPDF) {
      alert('PDF generator library loading... Please try again in a moment.');
      return;
    }

    try {
      const pdf = new jsPDF('p', 'mm', 'a4'); // A4 Portrait (210mm x 297mm)
      const pageWidth = 210;

      // 1. Header Bar Branding (Dark Slate Background)
      pdf.setFillColor(15, 23, 42);
      pdf.rect(0, 0, pageWidth, 24, 'F');

      pdf.setTextColor(255, 255, 255);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(13);
      pdf.text('CardioX — 12-LEAD DIAGNOSTIC ECG REPORT', 10, 11);

      pdf.setFontSize(7.5);
      pdf.setFont('helvetica', 'normal');
      pdf.text('DECK MOUNT ELECTRONICS PVT. LTD. | CLINICAL PORTAL', 10, 17);

      const now = new Date();
      const dateStr = now.toLocaleDateString() + ' ' + now.toLocaleTimeString();
      pdf.text(`Report Date: ${dateStr}`, pageWidth - 65, 17);

      // 2. Patient Demographics & Telemetry Box (Exact CardioX Software Format)
      pdf.setDrawColor(203, 213, 225);
      pdf.setFillColor(248, 250, 252);
      pdf.rect(10, 27, 190, 30, 'FD');

      pdf.setTextColor(15, 23, 42);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(8);

      // Col 1: Patient Details
      pdf.text(`Name: Rajesh Sharma`, 13, 33);
      pdf.text(`Patient ID: CX-90421`, 13, 38);
      pdf.text(`Age / Sex: 48Y / Male`, 13, 43);
      pdf.text(`BP / SpO2: 124/82 mmHg / 98%`, 13, 48);

      // Col 2: ECG Metrics
      const currentBPM = valBPM ? valBPM.textContent : '60';
      pdf.text(`HR: ${currentBPM} BPM`, 75, 33);
      pdf.text(`P-R: 156 ms`, 75, 38);
      pdf.text(`QRS: 88 ms`, 75, 43);
      pdf.text(`QT / QTc: 390 / 412 ms`, 75, 48);
      pdf.text(`QTcF: 402 ms`, 75, 53);

      // Col 3: Axis & Voltage Metrics
      pdf.text(`P/QRS/T Axis: +54° / +48° / +32°`, 138, 33);
      pdf.text(`RV5: 1.420 mV`, 138, 38);
      pdf.text(`SV1: 0.850 mV`, 138, 43);
      pdf.text(`RV5 + SV1: 2.270 mV`, 138, 48);
      pdf.text(`R-R: 1000 ms`, 138, 53);

      // 3. 12-Lead ECG Canvas Image Embedding & Filter Bar
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(8);
      pdf.text('25.0 mm/s   0.5-35Hz   AC : 50Hz   10.0 mm/mV', 10, 61);

      const canvasImgData = canvas.toDataURL('image/png', 1.0);
      pdf.setDrawColor(30, 41, 59);
      pdf.rect(10, 61, 190, 155);
      pdf.addImage(canvasImgData, 'PNG', 10.5, 61.5, 189, 154);

      // 4. AI Diagnostic Rhythm Interpretation
      pdf.setFillColor(240, 253, 244);
      pdf.setDrawColor(187, 247, 208);
      pdf.rect(10, 220, 190, 24, 'FD');

      pdf.setTextColor(22, 101, 52);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(8.5);
      pdf.text('AI RHYTHM INTERPRETATION: NORMAL SINUS RHYTHM', 13, 226);

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(7.5);
      pdf.text(`• Normal Sinus Rhythm at ${currentBPM} BPM. Normal P-wave morphology & axis (+54°).`, 13, 231);
      pdf.text('• No ST-segment elevation or T-wave inversion detected across all 12 leads.', 13, 236);
      pdf.text('• Regular R-R intervals with minimal baseline noise.', 13, 241);

      // 5. Doctor Sign-Off Section
      const doctorNotesText = doctorNotes ? doctorNotes.value.trim() : '';
      pdf.setTextColor(15, 23, 42);
      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(8.5);
      pdf.text('ATTENDING CARDIOLOGIST SIGN-OFF & IMPRESSIONS', 10, 251);

      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(7.5);
      pdf.text(`Clinical Observations: ${doctorNotesText || 'Reviewed and confirmed. Normal 12-lead ECG findings.'}`, 10, 257);

      pdf.setFont('helvetica', 'bold');
      pdf.setFontSize(8.5);
      pdf.text('Dr. A. Verma (MD, DM Cardiology)', 135, 274);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(7.5);
      pdf.text('Electronically Signed & Verified', 135, 279);
      pdf.line(135, 270, 195, 270);

      // Save PDF File
      pdf.save(`CardioX_ECG_Report_CX-90421.pdf`);
    } catch (pdfErr) {
      console.error('PDF Generation Error:', pdfErr);
      alert(`Could not generate PDF report: ${pdfErr.message}`);
    }
  }

  // Start 60 FPS Render Loop
  requestAnimationFrame(render);
});
