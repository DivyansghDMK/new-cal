"""
ECG Filter Module - Medical-Grade Filtering for ECG Signals

This module provides medical-grade filtering for ECG signals:
- Respiration-Preserving Baseline Correction (MONITOR-GRADE): Removes motion/electrode drift while preserving respiration
- Baseline Wander Removal (GOLD STANDARD): Median + Mean filter (commercial ECG monitor standard)
- AC Filter: Notch filter to remove 50Hz or 60Hz power line interference
- EMG Filter: High-pass filter to remove muscle artifacts (25Hz, 35Hz, 40Hz, 75Hz, 100Hz, 150Hz)
- DFT Filter: High-pass filter to remove baseline wander (0.05Hz, 0.5Hz)

Usage:
    from ecg.ecg_filters import apply_ecg_filters, ecg_with_respiratory_baseline
    
    # MONITOR-GRADE: Respiration-preserving baseline correction (RECOMMENDED)
    clean_ecg, respiration = ecg_with_respiratory_baseline(signal, sampling_rate=500)
    
    # GOLD STANDARD: Median + Mean filter for baseline removal
    clean_signal = apply_baseline_wander_median_mean(signal, sampling_rate=500)
    
    # Or use full filter chain
    filtered_signal = apply_ecg_filters(
        signal, 
        sampling_rate=500,
        ac_filter="50",  # "off", "50", or "60"
        emg_filter="150",  # "25", "35", "40", "75", "100", "150"
        dft_filter="0.5"  # "off", "0.05", or "0.5"
    )
"""

import numpy as np
import re
from scipy.signal import butter, filtfilt, iirnotch, medfilt, find_peaks
from scipy.ndimage import uniform_filter1d
from typing import Union, Optional, Tuple


def normalize_adc_signal(signal: np.ndarray, preserve_amplitude: bool = True) -> np.ndarray:
    """
    Normalize ADC signal at the very start of processing pipeline.
    Removes DC offset only (variance normalization disabled to prevent instability).
    
    Algorithm:
    1. Remove DC offset (mean subtraction)
    2. DO NOT normalize variance (preserves signal amplitude, prevents flickering)
    
    Args:
        signal: Raw ADC signal
        preserve_amplitude: If True, only remove DC offset (default: True)
    
    Returns:
        Normalized signal (zero mean, original amplitude preserved)
    """
    signal = np.asarray(signal, dtype=float)
    
    if len(signal) == 0:
        return signal
    
    # Remove DC offset only (do NOT normalize variance to prevent instability)
    normalized = signal - np.mean(signal)
    
    # Variance normalization disabled - causes waves to "come and go" when applied to sliding windows
    # The variance changes between updates, causing amplitude instability
    
    return normalized


def detect_qrs_regions(ecg: np.ndarray, fs: float = 500.0) -> np.ndarray:
    """
    Detect QRS regions for gated sharpening.
    Returns boolean mask: True in QRS regions, False elsewhere.
    
    Algorithm:
    1. Find R-peaks using peak detection
    2. Create QRS windows (±80 ms around each R-peak)
    3. Return mask indicating QRS regions
    
    Args:
        ecg: ECG signal
        fs: Sampling rate (Hz)
    
    Returns:
        Boolean array: True where QRS regions are located
    """
    if len(ecg) < 10:
        return np.zeros(len(ecg), dtype=bool)
    
    try:
        # Find R-peaks (simple peak detection)
        # Use absolute value to handle inverted leads
        abs_ecg = np.abs(ecg)
        threshold = np.percentile(abs_ecg, 75)  # 75th percentile as threshold
        
        # Find peaks with minimum distance (corresponds to ~200 BPM max)
        min_distance = int(0.3 * fs)  # 300 ms minimum between peaks
        
        peaks, _ = find_peaks(abs_ecg, height=threshold, distance=min_distance)
        
        # Create QRS region mask (±80 ms around each R-peak)
        qrs_window_ms = 80.0  # ±80 ms QRS window
        qrs_window_samples = int(qrs_window_ms * fs / 1000.0)
        
        mask = np.zeros(len(ecg), dtype=bool)
        for peak_idx in peaks:
            start = max(0, peak_idx - qrs_window_samples)
            end = min(len(ecg), peak_idx + qrs_window_samples + 1)
            mask[start:end] = True
        
        return mask
    except Exception:
        # Fallback: return all False (no sharpening)
        return np.zeros(len(ecg), dtype=bool)


def sharpen_qrs_gated(ecg: np.ndarray, fs: float = 500.0, alpha: float = 0.3) -> np.ndarray:
    """
    Sharpen QRS complexes with gating - only applies to QRS regions, not P or T waves.
    Monitor-grade: Preserves ST segment and QT interval.
    
    Algorithm:
    1. Detect QRS regions
    2. Calculate first derivative (highlights QRS edges)
    3. Apply sharpening only in QRS regions
    4. Leave P and T waves unchanged
    
    Args:
        ecg: EMG-suppressed ECG signal
        fs: Sampling rate (Hz)
        alpha: Sharpening factor (0.2-0.4, default 0.3)
    
    Returns:
        Sharpened ECG with preserved P and T waves
    """
    if len(ecg) < 3:
        return ecg
    
    try:
        # Detect QRS regions
        qrs_mask = detect_qrs_regions(ecg, fs)
        
        if not np.any(qrs_mask):
            # No QRS detected, return original
            return ecg
        
        # Calculate first derivative (emphasizes QRS edges)
        dt = 1.0 / fs
        derivative = np.gradient(ecg, dt)
        
        # Normalize derivative to prevent amplitude distortion
        if np.std(derivative) > 1e-10:
            derivative = derivative / np.std(derivative) * np.std(ecg)
        
        # Apply sharpening only in QRS regions
        sharpened = ecg.copy()
        sharpened[qrs_mask] = ecg[qrs_mask] + alpha * derivative[qrs_mask]
        
        return sharpened
    except Exception:
        return ecg


# ─── Filter implementation modes ─────────────────────────────────────────────
# "adaptive" cancels mains with an LMS estimator (what commercial carts do): it
# subtracts a tracked 50/60 Hz sinusoid instead of notching a whole band, so the
# QRS spectrum is untouched. "notch" is the previous fixed IIR notch.
AC_FILTER_MODE = "adaptive"

# "fir" uses a linear-phase FIR low-pass for the muscle filter; "butter" is the
# previous 4th-order Butterworth.
EMG_FILTER_TYPE = "butter"

# Baseline estimator for the DFT 0.5 setting:
#   "median2"     two median passes (200 ms then 600 ms) — the published
#                 Van Alsté method commercial carts descend from
#   "spline"      one anchor per beat on the PQ segment, cubic-spline baseline
#                 (Meyer & Keiser) — keeps genuine ST shift intact
#   "median_mean" the previous median(120 ms) + moving-average implementation
BASELINE_METHOD = "spline"
# Only used by "median_mean": size the averaging window from the measured RR.
BASELINE_RR_ADAPTIVE = False


def apply_ac_filter_adaptive(signal: np.ndarray, sampling_rate: float,
                             notch_freq: float = 50.0, window_s: float = 1.0,
                             blank_qrs: bool = True) -> np.ndarray:
    """Cancel mains by least-squares fitting the interference and subtracting it.

    In each overlapping window the amplitude and phase of the mains tone are found
    by projecting the signal onto cos/sin at notch_freq, using only samples OUTSIDE
    the QRS complexes so the spike cannot bias the fit. Only that one sinusoid is
    removed, so unlike a notch nothing else in the QRS spectrum is touched and no
    ringing is injected around sharp edges. Windows are cross-faded so the
    amplitude can track drift without a step at the seams.
    """
    x = np.asarray(signal, dtype=float)
    n = x.size
    if n < int(0.5 * sampling_rate):
        return x
    try:
        t = np.arange(n) / float(sampling_rate)
        c = np.cos(2.0 * np.pi * notch_freq * t)
        s_ = np.sin(2.0 * np.pi * notch_freq * t)

        usable = np.ones(n, dtype=bool)
        if blank_qrs:
            try:
                # Find the QRS complexes on a 5-35 Hz view of the signal, NOT on the
                # raw trace: detect_qrs_regions() thresholds by amplitude percentile,
                # so strong mains would have its own peaks flagged as QRS. Excluding
                # those from the fit removes exactly the samples that carry the
                # interference and the estimate collapses.
                b_qrs, a_qrs = butter(2, [5.0 / (sampling_rate / 2.0),
                                          35.0 / (sampling_rate / 2.0)], btype='band')
                qrs_view = filtfilt(b_qrs, a_qrs, x - np.mean(x))
                mask = detect_qrs_regions(qrs_view, sampling_rate)
                # Never blank so much that the fit loses the interference: the QRS
                # occupies ~10% of a beat, so anything past a third is a bad mask.
                if mask.sum() > n // 3:
                    mask = np.zeros(n, dtype=bool)
                usable = ~mask
            except Exception:
                usable = np.ones(n, dtype=bool)

        win = max(int(window_s * sampling_rate), int(0.2 * sampling_rate))
        hop = max(win // 2, 1)
        est = np.zeros(n)
        wsum = np.zeros(n)
        for start in range(0, max(n - win, 0) + 1, hop):
            end = min(start + win, n)
            seg = slice(start, end)
            m = usable[seg]
            if m.sum() < 20:
                m = np.ones(end - start, dtype=bool)
            cs, ss = c[seg][m], s_[seg][m]
            y = x[seg][m] - np.mean(x[seg][m])
            # 2x2 normal equations for A*cos + B*sin
            a11 = float(cs @ cs); a12 = float(cs @ ss); a22 = float(ss @ ss)
            det = a11 * a22 - a12 * a12
            if abs(det) < 1e-9:
                continue
            b1 = float(cs @ y); b2 = float(ss @ y)
            A = (a22 * b1 - a12 * b2) / det
            B = (a11 * b2 - a12 * b1) / det
            taper = np.hanning(end - start) + 1e-6
            est[seg] += (A * c[seg] + B * s_[seg]) * taper
            wsum[seg] += taper
        wsum[wsum == 0] = 1.0
        return x - est / wsum
    except Exception as e:
        print(f" Adaptive AC filter failed ({e}) — falling back to notch")
        return signal


def apply_ac_filter(signal: np.ndarray, sampling_rate: float, ac_filter: str) -> np.ndarray:
    """
    Apply AC (Notch) Filter to remove power line interference
    
    Args:
        signal: Input ECG signal
        sampling_rate: Sampling frequency in Hz
        ac_filter: "off", "50", or "60" (Hz)
    
    Returns:
        Filtered signal
    """
    if ac_filter == "off" or not ac_filter:
        return signal
    
    try:
        ac_text = str(ac_filter).strip().lower()
        match = re.search(r"(\d+(?:\.\d+)?)", ac_text)
        notch_freq = float(match.group(1)) if match else float(ac_filter)  # 50 or 60 Hz
        
        # Design notch filter (bandstop filter)
        nyquist = sampling_rate / 2.0
        quality_factor = 5.0  # Reduced from 10 to minimize ringing and transients
        # Quality factor for notch filter (lower Q = less ringing, faster transient response)
        
        # Normalize frequency
        w0 = notch_freq / nyquist
        
        # Ensure frequency is within valid range (0 < w0 < 1)
        if w0 <= 0 or w0 >= 1:
            print(f" AC filter frequency {notch_freq}Hz is invalid for sampling rate {sampling_rate}Hz")
            return signal
        
        if str(AC_FILTER_MODE).lower() == "adaptive":
            return apply_ac_filter_adaptive(signal, sampling_rate, notch_freq)

        # Design IIR notch filter and convert to SOS for numerical stability
        b, a = iirnotch(w0, quality_factor)
        from scipy.signal import tf2sos, sosfiltfilt
        sos = tf2sos(b, a)
        
        # Apply filter (zero-phase) with reflect padding to minimize transients
        pad_len = min(len(signal) // 3, int(2 * sampling_rate)) if len(signal) > 0 else 0
        if pad_len > 0:
            padded = np.pad(signal, (pad_len, pad_len), mode="reflect")
            filtered_padded = sosfiltfilt(sos, padded)
            filtered_signal = filtered_padded[pad_len:-pad_len]
        else:
            filtered_signal = sosfiltfilt(sos, signal)
        
        return filtered_signal
    
    except Exception as e:
        print(f" Error applying AC filter ({ac_filter}Hz): {e}")
        return signal


def stabilize_report_edges(signal: np.ndarray, sampling_rate: float, edge_ms: float = 180.0) -> np.ndarray:
    """
    Reduce edge transients in report strips so the waveform ends smoothly
    (no visible terminal jump/spike in printed reports).
    """
    arr = np.asarray(signal, dtype=float)
    if arr.size < 20:
        return arr

    try:
        fs = float(sampling_rate)
    except Exception:
        fs = 500.0
    if fs <= 0:
        fs = 500.0

    edge_n = max(8, int((edge_ms / 1000.0) * fs))
    edge_n = min(edge_n, max(8, arr.size // 6))
    if edge_n * 3 >= arr.size:
        return arr

    stable_tail_start = arr.size - (3 * edge_n)
    stable_tail_end = arr.size - edge_n
    stable_head_start = edge_n
    stable_head_end = 3 * edge_n

    head_target = float(np.median(arr[stable_head_start:stable_head_end]))
    tail_target = float(np.median(arr[stable_tail_start:stable_tail_end]))

    out = arr.copy()
    ramp = np.linspace(0.0, 1.0, edge_n, endpoint=True)
    out[:edge_n] = (1.0 - ramp) * head_target + ramp * out[:edge_n]
    out[-edge_n:] = (1.0 - ramp) * out[-edge_n:] + ramp * tail_target
    return out


# ─── Front-end droop compensation (square-wave / calibration work) ────────────
# The acquisition front end is AC-coupled with a ~0.49 s time constant (~0.32 Hz),
# so a true square input prints with a sagging top. That sag is created BEFORE the
# samples reach this software — it cannot be "switched off" here, only inverted.
#
# Set BASELINE_RESTORE_TAU_S to the measured time constant (0.49) to reconstruct the
# original square; leave it at 0.0 to disable. Keep it OFF for patient recordings:
# the inverse of a high-pass is an integrator, so electrode drift and motion that the
# front end removes would be amplified back into the trace.
BASELINE_RESTORE_TAU_S = 0.0


def restore_frontend_droop(signal, sampling_rate: float = 500.0, tau_s: float = None) -> np.ndarray:
    """Invert the front end's first-order high-pass so square inputs print flat."""
    tau = BASELINE_RESTORE_TAU_S if tau_s is None else tau_s
    sig = np.asarray(signal, dtype=float)
    if not tau or tau <= 0 or sig.size < 4:
        return sig
    try:
        centred = sig - np.mean(sig)
        restored = centred + np.cumsum(centred) / (float(sampling_rate) * float(tau))
        # The integrator adds a slow ramp; remove it so the strip stays centred.
        idx = np.arange(restored.size, dtype=float)
        restored = restored - np.polyval(np.polyfit(idx, restored, 1), idx)
        return restored + np.mean(sig)
    except Exception:
        return sig


# ─── EMG stage master switch ──────────────────────────────────────────────────
# The Set Filter dialog offers no "off" option for the EMG (muscle-artifact
# low-pass), so it is disabled here in code. Set back to True to restore it —
# every caller (live display, 12-lead report, HRV/hyperkalemia reports) honours
# this flag because they all route through apply_emg_filter().
EMG_FILTER_ENABLED = True


def apply_emg_filter(signal: np.ndarray, sampling_rate: float, emg_filter: str) -> np.ndarray:
    """
    Apply EMG Filter (Low-pass filter) to suppress muscle artifacts.
    CORRECTED: Uses 35-40 Hz low-pass instead of high-pass to preserve QRS while removing EMG noise.
    
    Args:
        signal: Input ECG signal
        sampling_rate: Sampling frequency in Hz
        emg_filter: Cutoff frequency - "25", "35", "40", "75", "100", or "150" (Hz)
    
    Returns:
        Filtered signal
    """
    if not EMG_FILTER_ENABLED:
        return signal

    if not emg_filter or emg_filter == "off":
        return signal
    
    try:
        cutoff_freq = float(emg_filter)
        nyquist = sampling_rate / 2.0

        # Safety: if sampling_rate is unexpectedly low, fall back to 500 Hz
        if sampling_rate < 100:  # hardware should be 500 Hz; avoid unstable filters
            nyquist = 500.0 / 2.0
            sampling_rate = 500.0

        # Clamp cutoff so it is always below Nyquist for a valid low‑pass filter
        max_allowed = nyquist * 0.9
        if cutoff_freq >= max_allowed:
            cutoff_freq = max_allowed
        if cutoff_freq <= 0:
            return signal

        # Normalize cutoff frequency
        normalized_cutoff = cutoff_freq / nyquist
        
        if str(EMG_FILTER_TYPE).lower() == "fir":
            # Linear-phase FIR: symmetric impulse response, so the group delay is
            # constant and the passband edge does not overshoot asymmetrically the
            # way an IIR does on a sharp QRS. Kaiser window trades ripple for a
            # slightly wider transition, which is the right trade for ECG.
            from scipy.signal import firwin
            numtaps = int(round(4.0 * sampling_rate / max(cutoff_freq, 1.0)))
            numtaps = max(21, min(numtaps | 1, max(21, (len(signal) // 3) | 1)))
            taps = firwin(numtaps, cutoff_freq, window=('kaiser', 6.0), fs=sampling_rate)
            return filtfilt(taps, [1.0], signal)

        # Design 4th order low-pass Butterworth filter (zero-phase)
        b, a = butter(4, normalized_cutoff, btype='low')
        
        # Apply filter (zero-phase filtering)
        filtered_signal = filtfilt(b, a, signal)
        
        return filtered_signal
    
    except Exception as e:
        print(f" Error applying EMG filter ({emg_filter}Hz): {e}")
        return signal


def apply_dft_filter(signal: np.ndarray, sampling_rate: float, dft_filter: str) -> np.ndarray:
    """
    Apply DFT Filter (High-pass filter) to remove baseline wander
    
    Args:
        signal: Input ECG signal
        sampling_rate: Sampling frequency in Hz
        dft_filter: Cutoff frequency - "off", "0.05", or "0.5" (Hz)
    
    Returns:
        Filtered signal
    """
    if dft_filter == "off" or not dft_filter:
        return signal
    
    try:
        if str(dft_filter).strip() == "0.5":
            # Gold Standard: use median+mean filter for 0.5 Hz baseline removal
            # This is extremely stable and prevents baseline drift/wander entirely.
            return apply_baseline_wander_median_mean(signal, sampling_rate)

        cutoff_freq = float(dft_filter)  # Low cutoff frequency (0.05 or 0.5 Hz)
        
        # Design high-pass Butterworth filter for baseline wander removal
        nyquist = sampling_rate / 2.0
        
        # Normalize cutoff frequency
        normalized_cutoff = cutoff_freq / nyquist
        
        # Ensure cutoff is within valid range
        if normalized_cutoff <= 0 or normalized_cutoff >= 1:
            print(f" DFT filter cutoff {cutoff_freq}Hz is invalid for sampling rate {sampling_rate}Hz")
            return signal
        
        # Design 2nd order high-pass Butterworth filter (gentle for baseline)
        b, a = butter(2, normalized_cutoff, btype='high')
        
        # Apply filter (zero-phase filtering)
        filtered_signal = filtfilt(b, a, signal)
        
        return filtered_signal
    
    except Exception as e:
        print(f" Error applying DFT filter ({dft_filter}Hz): {e}")
        return signal


def process_cardiox_grade(ecg: np.ndarray, fs: float = 500.0, apply_sharpening: bool = False) -> np.ndarray:
    """
    Complete monitor-grade ECG processing pipeline with all corrections.
    
    Pipeline order:
    1. ADC normalization (DC offset removal only - variance preserved to prevent instability)
    2. Powerline removal (50 Hz notch, Q=25)
    3. Baseline correction (respiration preserved, 120 ms median)
    4. EMG suppression (35-40 Hz low-pass)
    5. QRS sharpening (gated, only in QRS regions) - OPTIONAL to prevent instability
    
    Args:
        ecg: Raw ECG ADC signal
        fs: Sampling rate (Hz, default 500)
        apply_sharpening: If True, apply QRS sharpening (default: False to prevent instability)
    
    Returns:
        Processed ECG with sharp P-QRS-T waves, preserved ST/QT
    """
    ecg = np.asarray(ecg, dtype=float)
    
    if len(ecg) < 10:
        return ecg
    
    # Step 1: ADC normalization (remove DC offset only - preserve amplitude to prevent flickering)
    ecg = normalize_adc_signal(ecg, preserve_amplitude=True)
    
    # Step 2: Remove powerline interference (50 Hz, Q=25 to avoid ringing)
    ecg = notch_filter_butterworth(ecg, fs, freq=50.0, q=25.0)
    
    # Step 3: Correct baseline (preserve respiration, 120 ms median to avoid QRS erosion)
    ecg, _ = ecg_with_respiratory_baseline(ecg, fs)
    
    # Step 4: Suppress EMG noise (35-40 Hz low-pass, not high-pass)
    ecg = apply_emg_filter(ecg, fs, "35")
    
    # Step 5: Sharpen QRS (gated, only in QRS regions, preserves P/T waves)
    # DISABLED by default - can cause instability if QRS detection is inconsistent
    if apply_sharpening:
        ecg = sharpen_qrs_gated(ecg, fs, alpha=0.3)
    
    return ecg


def apply_ecg_filters(
    signal: Union[np.ndarray, list],
    sampling_rate: float = 500,
    ac_filter: Optional[str] = None,
    emg_filter: Optional[str] = None,
    dft_filter: Optional[str] = None
) -> np.ndarray:
    """
    Apply all ECG filters in the correct order:
    1. DFT Filter (baseline wander removal) - first
    2. EMG Filter (muscle artifact removal)
    3. AC Filter (power line interference removal) - last
    
    Args:
        signal: Input ECG signal (numpy array or list)
        sampling_rate: Sampling frequency in Hz (default: 500)
        ac_filter: AC filter setting - "off", "50", or "60"
        emg_filter: EMG filter setting - "25", "35", "40", "75", "100", "150"
        dft_filter: DFT filter setting - "off", "0.05", or "0.5"
    
    Returns:
        Filtered signal as numpy array
    """
    # Convert to numpy array if needed
    if not isinstance(signal, np.ndarray):
        signal = np.array(signal, dtype=float)
    
    # Check minimum signal length
    if len(signal) < 10:
        return signal
    
    # Apply filters in correct order
    filtered = signal.copy()
    
    # 1. DFT Filter first (removes slow baseline wander)
    if dft_filter:
        filtered = apply_dft_filter(filtered, sampling_rate, dft_filter)
    
    # 2. EMG Filter second (removes muscle artifacts) — only when selected
    if EMG_FILTER_ENABLED and emg_filter and str(emg_filter).lower() != "off":
        filtered = apply_emg_filter(filtered, sampling_rate, emg_filter)

    # 3. AC Filter last (removes power line interference).
    # Applied whenever the user selected it. It used to be skipped silently when the
    # EMG cutoff was under 60 Hz, so the header claimed a notch that never ran.
    if ac_filter:
        filtered = apply_ac_filter(filtered, sampling_rate, ac_filter)
    
    return filtered


def _estimate_rr_ms(signal: np.ndarray, sampling_rate: float = 500.0):
    """Median RR in ms from a quick slope-based R detection; None if unreliable."""
    x = np.asarray(signal, dtype=float)
    if x.size < int(sampling_rate):
        return None
    d = np.abs(np.diff(x))
    thr = np.percentile(d, 99.0)
    if not np.isfinite(thr) or thr <= 0:
        return None
    idx = np.flatnonzero(d > thr)
    if idx.size < 3:
        return None
    peaks, group = [], [idx[0]]
    min_gap = int(0.20 * sampling_rate)
    for k in idx[1:]:
        if k - group[-1] <= min_gap:
            group.append(k)
        else:
            peaks.append(group[0]); group = [k]
    peaks.append(group[0])
    if len(peaks) < 3:
        return None
    rr = np.diff(np.asarray(peaks, dtype=float)) / float(sampling_rate) * 1000.0
    rr = rr[(rr > 250.0) & (rr < 2500.0)]
    return float(np.median(rr)) if rr.size else None


def apply_baseline_spline(signal: np.ndarray, sampling_rate: float = 500.0) -> np.ndarray:
    """Beat-synchronous baseline removal (Meyer & Keiser cubic-spline method).

    One anchor per beat is taken from the PQ segment — the isoelectric stretch
    just before the QRS — and a cubic spline through those anchors becomes the
    baseline estimate. Because every anchor sits on an isoelectric point and none
    sit on the ST segment, genuine ST elevation or depression passes through
    untouched, which a moving average or a median cannot guarantee.
    """
    x = np.asarray(signal, dtype=float)
    n = x.size
    if n < int(sampling_rate):
        return x
    try:
        d = np.abs(np.diff(x))
        thr = np.percentile(d, 99.0)
        idx = np.flatnonzero(d > thr)
        if idx.size < 3:
            return x - np.mean(x)
        peaks, group = [], [idx[0]]
        min_gap = int(0.20 * sampling_rate)
        for k in idx[1:]:
            if k - group[-1] <= min_gap:
                group.append(k)
            else:
                peaks.append(group[0]); group = [k]
        peaks.append(group[0])
        peaks = [p for p in peaks if p > int(0.08 * sampling_rate)]
        if len(peaks) < 3:
            return x - np.mean(x)

        # PQ window: 60 ms to 20 ms before the QRS onset marker
        a, b = int(0.060 * sampling_rate), int(0.020 * sampling_rate)
        xs, ys = [], []
        for p_i in peaks:
            lo, hi = max(0, p_i - a), max(1, p_i - b)
            if hi - lo >= 3:
                xs.append(0.5 * (lo + hi))
                ys.append(float(np.median(x[lo:hi])))
        if len(xs) < 3:
            return x - np.mean(x)

        from scipy.interpolate import CubicSpline
        cs = CubicSpline(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float),
                         extrapolate=True)
        baseline = cs(np.arange(n, dtype=float))
        return x - baseline
    except Exception as e:
        print(f" Spline baseline failed ({e})")
        return signal


def apply_baseline_wander_median_mean(signal: np.ndarray, sampling_rate: float = 500) -> np.ndarray:
    """
    GOLD STANDARD: Median Filter + Mean Filter for baseline wander removal
    Used in many commercial ECG monitors.
    
    Why it's special:
    - Removes baseline without touching QRS or ST segments
    - No phase distortion
    - Excellent for real-time display
    
    Algorithm:
    1. Median filter (200-300 ms) → removes QRS influence
    2. Moving average (600-1000 ms) → smooths baseline
    3. Subtract baseline from original signal
    
    Typical parameters (500 Hz):
    - Median filter: 200-300 ms (100-150 samples)
    - Mean filter: 600-1000 ms (300-500 samples)
    
    Args:
        signal: Input ECG signal
        sampling_rate: Sampling frequency in Hz (default: 500)
    
    Returns:
        Clean ECG signal with baseline wander removed
    """
    if len(signal) < 50:  # Need minimum samples
        return signal - np.mean(signal)
    
    try:
        # Step 1: Median filter (120 ms window - reduced from 200 ms to avoid QRS erosion)
        median_window_ms = 120.0  # milliseconds
        median_window = int(median_window_ms * sampling_rate / 1000.0)
        median_window = max(3, min(median_window, len(signal) // 2))  # Ensure odd and reasonable
        
        # Make window odd (required for median filter)
        if median_window % 2 == 0:
            median_window += 1
        
        # Apply median filter to remove QRS influence
        b1 = medfilt(signal, kernel_size=median_window)
        
        # Step 2: Moving average — sized from the beat, not fixed.
        # A fixed 800 ms window spans more than one RR above ~75 bpm, which lets
        # QRS/T energy into the baseline estimate and lifts the whole ST segment
        # (measured: +0.56 mV of false ST elevation at 120 bpm).
        # Use 800 ms as middle value: 0.8 * Fs
        if str(BASELINE_METHOD).lower() == "spline":
            return apply_baseline_spline(signal, sampling_rate)

        if str(BASELINE_METHOD).lower() == "median2":
            # Two median passes: the first is longer than a QRS so the spike cannot
            # survive it, the second is longer than a T wave. Medians ignore the
            # tall/brief features entirely, where a moving average averages them in
            # and drags the ST segment with it.
            def _odd(v):
                v = int(max(3, v));  return v + 1 if v % 2 == 0 else v
            w1 = _odd(0.200 * sampling_rate)
            w2 = _odd(0.600 * sampling_rate)
            w1 = min(w1, _odd(len(signal) // 2)); w2 = min(w2, _odd(len(signal) // 2))
            base = medfilt(medfilt(signal, kernel_size=w1), kernel_size=w2)
            return signal - base

        mean_window_ms = 800.0
        if BASELINE_RR_ADAPTIVE:
            try:
                rr_ms = _estimate_rr_ms(signal, sampling_rate)
                if rr_ms:
                    # Stay inside one beat: 80% of RR, clamped to a sane range.
                    mean_window_ms = float(np.clip(0.8 * rr_ms, 200.0, 800.0))
            except Exception:
                mean_window_ms = 800.0  # milliseconds
        mean_window = int(mean_window_ms * sampling_rate / 1000.0)
        mean_window = max(10, min(mean_window, len(b1) // 2))  # Ensure reasonable
        
        # Apply moving average to smooth baseline
        baseline = uniform_filter1d(b1.astype(float), size=mean_window, mode='nearest')
        
        # Step 3: Subtract baseline from original signal
        clean_ecg = signal - baseline
        
        return clean_ecg
    
    except Exception as e:
        print(f" Error applying median+mean baseline filter: {e}")
        # Fallback: simple mean subtraction
        return signal - np.mean(signal)


def notch_filter_butterworth(ecg: np.ndarray, fs: float, freq: float = 50.0, q: float = 25.0) -> np.ndarray:
    """
    Notch filter using Butterworth design (for India → 50 Hz)
    
    Args:
        ecg: Input ECG signal
        fs: Sampling frequency in Hz
        freq: Notch frequency (default: 50.0 Hz for India)
        q: Quality factor (default: 30.0)
    
    Returns:
        Filtered signal with powerline noise removed
    """
    if len(ecg) < 10:
        return ecg
    
    try:
        w0 = freq / (fs / 2.0)
        if w0 <= 0 or w0 >= 1:
            return ecg
        
        b, a = butter(2, [w0 - w0/q, w0 + w0/q], btype='bandstop')
        return filtfilt(b, a, ecg)
    except Exception as e:
        print(f" Error applying notch filter: {e}")
        return ecg


def estimate_baseline_drift(ecg: np.ndarray, fs: float) -> np.ndarray:
    """
    Estimate baseline drift (motion + electrode drift) using median + mean filter.
    This is the clinical gold standard method.
    
    Algorithm:
    1. Median filter (200 ms) → removes QRS influence
    2. Moving average (1.8 s) → smooths baseline drift
    
    Args:
        ecg: Input ECG signal
        fs: Sampling frequency in Hz
    
    Returns:
        Estimated baseline drift signal
    """
    if len(ecg) < 50:
        return np.zeros_like(ecg)
    
    try:
        # Median filter removes QRS influence (120 ms window - reduced from 200 ms to avoid QRS erosion)
        median_window = int(0.12 * fs) | 1  # Ensure odd
        if median_window < 3:
            median_window = 3
        if median_window > len(ecg) // 2:
            median_window = (len(ecg) // 2) | 1
        
        med = medfilt(ecg, kernel_size=median_window)
        
        # Moving average removes remaining slow drift (1.8 s window)
        mean_window = int(1.8 * fs)
        if mean_window < 10:
            mean_window = 10
        if mean_window > len(med):
            mean_window = len(med)
        
        # Use convolution for moving average
        kernel = np.ones(mean_window) / mean_window
        drift = np.convolve(med, kernel, mode='same')
        
        return drift
    except Exception as e:
        print(f" Error estimating baseline drift: {e}")
        return np.zeros_like(ecg)


def extract_respiration(drift_signal: np.ndarray, fs: float) -> np.ndarray:
    """
    Extract respiration component from baseline drift signal (EDR - ECG-Derived Respiration).
    CORRECTED: Extracts from drift signal, not raw ECG, for better accuracy.
    
    Respiration band: 0.1 - 0.35 Hz
    
    Args:
        drift_signal: Baseline drift signal (from estimate_baseline_drift)
        fs: Sampling frequency in Hz
    
    Returns:
        Respiration waveform (EDR) with safe amplitude scaling
    """
    if len(drift_signal) < 10:
        return np.zeros_like(drift_signal)
    
    try:
        # Low-pass filter at 0.35 Hz to extract respiration from drift signal
        nyquist = fs / 2.0
        cutoff = 0.35 / nyquist
        
        if cutoff <= 0 or cutoff >= 1:
            return np.zeros_like(drift_signal)
        
        b, a = butter(2, cutoff, btype='low')
        resp = filtfilt(b, a, drift_signal)
        
        # Remove DC offset
        resp = resp - np.mean(resp)
        
        # Safe amplitude scaling instead of hard clipping
        # Scale to ±0.6 mV range if amplitude exceeds threshold
        max_amplitude = np.max(np.abs(resp)) if len(resp) > 0 else 0.0
        if max_amplitude > 0.6:
            scale_factor = 0.6 / max_amplitude
            resp = resp * scale_factor
        
        return resp
    except Exception as e:
        print(f" Error extracting respiration: {e}")
        return np.zeros_like(drift_signal)


def ecg_with_respiratory_baseline(ecg: np.ndarray, fs: float = 500) -> Tuple[np.ndarray, np.ndarray]:
    """
    🫀 MONITOR-GRADE: ECG with Respiration-Controlled Baseline
    
    This is exactly how bedside ECG monitors behave:
    - ✅ Stable ECG baseline
    - ✅ Baseline moves only with respiration
    - ✅ Motion drift suppressed
    - ✅ Safe for ST segment
    - ✅ Real-time friendly
    
    Algorithm:
    1. Remove powerline noise (50 Hz notch for India)
    2. Estimate unwanted baseline drift (motion + electrode drift)
    3. Extract respiration component (0.1-0.35 Hz)
    4. Clamp respiration amplitude (prevents crazy baseline swing)
    5. Reconstruct ECG: clean_ecg = ecg_notched - drift + respiration
    
    Args:
        ecg: Input ECG signal
        fs: Sampling frequency in Hz (default: 500)
    
    Returns:
        tuple: (clean_ecg, respiration)
            - clean_ecg: Stable ECG with breathing baseline
            - respiration: Respiration waveform (EDR)
    
    Example:
        clean_ecg, respiration = ecg_with_respiratory_baseline(signal, fs=500)
        # clean_ecg: Flat baseline at rest, smooth sinusoidal motion while breathing
        # respiration: Can be used to calculate respiration rate
    """
    ecg = np.asarray(ecg, dtype=float)
    
    if len(ecg) < 50:
        # Too short for filtering, just center it
        centered = ecg - np.mean(ecg)
        return centered, np.zeros_like(centered)
    
    try:
        # 1. Remove powerline noise (50 Hz for India, Q=25 to avoid ringing)
        ecg_notched = notch_filter_butterworth(ecg, fs, freq=50.0, q=25.0)
        
        # 2. Estimate unwanted baseline drift (motion + electrode drift)
        drift = estimate_baseline_drift(ecg_notched, fs)
        
        # 3. Extract respiration component from drift signal (0.1-0.35 Hz)
        # CORRECTED: Extract from drift, not raw ECG, with safe amplitude scaling
        respiration = extract_respiration(drift, fs)
        
        # 5. Reconstruct ECG: remove drift, add back respiration
        clean_ecg = ecg_notched - drift + respiration
        
        return clean_ecg, respiration
    
    except Exception as e:
        print(f" Error in respiration-preserving baseline correction: {e}")
        # Fallback: simple mean subtraction
        centered = ecg - np.mean(ecg)
        return centered, np.zeros_like(centered)


def respiration_rate(resp: np.ndarray, fs: float) -> float:
    """
    Calculate respiration rate from respiration waveform (EDR).
    
    Args:
        resp: Respiration waveform (from extract_respiration or ecg_with_respiratory_baseline)
        fs: Sampling frequency in Hz
    
    Returns:
        Respiration rate in breaths per minute (BPM)
    """
    if len(resp) < 10:
        return 0.0
    
    try:
        # Count zero crossings (positive-going)
        zero_crossings = np.where(np.diff(np.sign(resp)) > 0)[0]
        breaths = len(zero_crossings)
        
        # Calculate duration in minutes
        duration_min = len(resp) / fs / 60.0
        
        if duration_min > 0:
            return breaths / duration_min
        else:
            return 0.0
    except Exception as e:
        print(f" Error calculating respiration rate: {e}")
        return 0.0


def apply_ecg_filters_from_settings(
    signal: Union[np.ndarray, list],
    sampling_rate: float = 500,
    settings_manager=None
) -> np.ndarray:
    """
    Apply ECG filters using settings from SettingsManager
    
    Args:
        signal: Input ECG signal
        sampling_rate: Sampling frequency in Hz
        settings_manager: SettingsManager instance (optional, will create if not provided)
    
    Returns:
        Filtered signal
    """
    # Import here to avoid circular imports
    if settings_manager is None:
        from utils.settings_manager import SettingsManager
        settings_manager = SettingsManager()
    
    # Get filter settings
    ac_filter = settings_manager.get_setting("filter_ac", "50")
    emg_filter = settings_manager.get_setting("filter_emg", "25")
    dft_filter = settings_manager.get_setting("filter_dft", "off")
    
    # Apply filters
    return apply_ecg_filters(
        signal=signal,
        sampling_rate=sampling_rate,
        ac_filter=ac_filter,
        emg_filter=emg_filter,
        dft_filter=dft_filter
    )
