import sys, os, json, argparse, numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

ECG_PAPER_BG   = "#fffdfd"
ECG_GRID_MINOR = "#f7dede"
ECG_GRID_MAJOR = "#efb9b9"
ADC_PER_MV     = 1.8
ECG_FS         = 500.0
FIXED_WAVE_GAIN = 10.0

def load_from_history(json_path, lead="II"):
    with open(json_path) as f:
        hist = json.load(f)
    records = hist if isinstance(hist, list) else list(hist.values())
    for rec in reversed(records):
        leads = rec.get("leads") or rec.get("lead_data") or {}
        if lead in leads and len(leads[lead]) > 500:
            print("  Loaded from history: record timestamp=%s" % rec.get("timestamp","?"))
            return np.array(leads[lead], dtype=float)
    raise ValueError("No usable Lead %s data found in %s" % (lead, json_path))

def load_from_csv(csv_path, col=1):
    data = []
    with open(csv_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            try:
                data.append(float(parts[col]))
            except Exception:
                continue
    if len(data) < 500:
        raise ValueError("CSV has too few samples (%d)" % len(data))
    print("  Loaded %d samples from %s" % (len(data), csv_path))
    return np.array(data, dtype=float)

def load_from_json(json_path, lead="II"):
    with open(json_path) as f:
        d = json.load(f)
    leads = d.get("leads", d)
    arr = leads.get(lead, [])
    if len(arr) < 500:
        raise ValueError("JSON Lead %s has too few samples (%d)" % (lead, len(arr)))
    print("  Loaded %d samples (Lead %s) from %s" % (len(arr), lead, json_path))
    return np.array(arr, dtype=float)

def generate_synthetic_ecg(n=5000, fs=500.0):
    t = np.arange(n) / fs
    hr_bpm = 72.0
    rr = 60.0 / hr_bpm
    signal = np.zeros(n)
    for beat_start in np.arange(0, t[-1], rr):
        p_c = beat_start + 0.12
        p_wave = 0.15 * np.exp(-0.5 * ((t - p_c) / 0.04) ** 2)
        q_c = beat_start + 0.22; r_c = beat_start + 0.25; s_c = beat_start + 0.28
        q_wave = -0.10 * np.exp(-0.5 * ((t - q_c) / 0.01) ** 2)
        r_wave =  1.00 * np.exp(-0.5 * ((t - r_c) / 0.02) ** 2)
        s_wave = -0.20 * np.exp(-0.5 * ((t - s_c) / 0.015) ** 2)
        t_c = beat_start + 0.42
        t_wave = 0.35 * np.exp(-0.5 * ((t - t_c) / 0.08) ** 2)
        signal += p_wave + q_wave + r_wave + s_wave + t_wave
    adc = signal * 1.8 * 1000 + 2000
    noise = np.random.normal(0, 15, n)
    print("  Using synthetic ECG (72 BPM, n=%d)" % n)
    return adc + noise

def run_qrs_pipeline(raw_signal, fs=ECG_FS, label="Lead II"):
    print("\n" + "="*60)
    print("  QRS CALCULATION PIPELINE -- %s" % label)
    print("="*60)
    results = {}

    signal_mv = raw_signal / ADC_PER_MV
    print("\n[Step 1] ADC -> mV")
    print("  ADC_PER_MV  = %.1f" % ADC_PER_MV)
    print("  Raw range   : [%.1f, %.1f] ADC" % (raw_signal.min(), raw_signal.max()))
    print("  mV  range   : [%.3f, %.3f] mV" % (signal_mv.min(), signal_mv.max()))
    results["raw_adc"]   = raw_signal
    results["signal_mv"] = signal_mv

    sorted_sig = np.sort(raw_signal)
    baseline   = sorted_sig[len(sorted_sig) // 2]
    centered   = raw_signal - baseline
    print("\n[Step 2] DC-offset removal (median baseline)")
    print("  Median baseline = %.2f ADC" % baseline)
    print("  Centered range  : [%.2f, %.2f] ADC" % (centered.min(), centered.max()))
    results["baseline"] = baseline
    results["centered"] = centered

    from scipy.signal import butter, filtfilt
    arr_dc = centered.astype(float)
    nyq = fs / 2.0
    low = max(0.5 / nyq, 0.001)
    high = min(40.0 / nyq, 0.99)
    b, a = butter(2, [low, high], "band")
    filt = filtfilt(b, a, arr_dc)
    print("\n[Step 3] Bandpass filter 0.5-40 Hz")
    print("  Filtered range  : [%.2f, %.2f] ADC" % (filt.min(), filt.max()))
    results["filtered"] = filt

    try:
        from ecg.pan_tompkins import pan_tompkins
        r_peaks = pan_tompkins(filt, fs=fs)
        method  = "Pan-Tompkins"
    except Exception as e:
        print("  Pan-Tompkins failed (%s), using fallback find_peaks" % e)
        from scipy.signal import find_peaks
        height_thr     = np.mean(filt) + 0.5 * np.std(filt)
        prominence_thr = np.std(filt) * 0.4
        r_peaks, _     = find_peaks(filt, height=height_thr,
                                    distance=int(0.35 * fs), prominence=prominence_thr)
        method = "find_peaks fallback"

    rr_all   = np.diff(r_peaks) * (1000.0 / fs)
    valid_rr = rr_all[(rr_all >= 200) & (rr_all <= 6000)]
    print("\n[Step 4] R-peak detection (%s)" % method)
    print("  R-peaks found  : %d" % len(r_peaks))
    print("  R-peak indices : %s" % r_peaks[:10].tolist())
    print("  All RR (ms)    : %s" % np.round(rr_all[:8], 1).tolist())
    results["r_peaks"]     = r_peaks
    results["rr_all_ms"]   = rr_all
    results["valid_rr_ms"] = valid_rr

    if len(valid_rr) == 0:
        print("  WARNING: No valid RR intervals -- stopping pipeline.")
        return results

    rr_median_ms = float(np.median(valid_rr))
    hr_bpm       = int(round(60000.0 / rr_median_ms))
    rr_sec       = rr_median_ms / 1000.0
    print("\n[Step 5] Heart Rate + RR")
    print("  Median RR  : %.1f ms" % rr_median_ms)
    print("  Heart Rate : %d BPM" % hr_bpm)
    results["hr_bpm"]       = hr_bpm
    results["rr_median_ms"] = rr_median_ms

    from ecg.ecg_calculations import calculateAdaptiveWindows
    windows = calculateAdaptiveWindows(hr_bpm, rr_sec, fs)
    print("\n[Step 6] Adaptive Windows (HR=%d BPM)" % hr_bpm)
    print("  minPtoQRS      : %d smp  (%.1f ms)" % (windows.minPtoQRS, windows.minPtoQRS/fs*1000))
    print("  maxPtoQRS      : %d smp  (%.1f ms)" % (windows.maxPtoQRS, windows.maxPtoQRS/fs*1000))
    print("  pSearchWindow  : %d smp  (%.1f ms)" % (windows.pSearchWindow, windows.pSearchWindow/fs*1000))
    print("  qrsOnsetSearch : %d smp  (%.1f ms)" % (windows.qrsOnsetSearch, windows.qrsOnsetSearch/fs*1000))
    print("  qrsOffsetFromR : %d smp  (%.1f ms)" % (windows.qrsOffsetFromR, windows.qrsOffsetFromR/fs*1000))
    print("  tSearchStart   : %d smp  (%.1f ms)" % (windows.tSearchStart, windows.tSearchStart/fs*1000))
    print("  tSearchEnd     : %d smp  (%.1f ms)" % (windows.tSearchEnd, windows.tSearchEnd/fs*1000))
    results["windows"] = windows

    from ecg.qrs_detection import qrs_duration_from_raw_signal
    from ecg.ecg_calculations import detectQRSStartAdaptive, detectQRSEndAdaptive
    r_curr = int(r_peaks[-2]) if len(r_peaks) >= 2 else int(r_peaks[-1])
    qrs_per_beat=[]; qrs_start_idxs=[]; qrs_end_idxs=[]
    for rp in r_peaks[1:-1]:
        rp = int(rp)
        try:
            qrs_ms = qrs_duration_from_raw_signal(filt, rp, fs, adc_per_mv=1200.0, heart_rate=hr_bpm)
            qs = detectQRSStartAdaptive(filt, rp, windows)
            qe = detectQRSEndAdaptive(filt, rp, windows)
            if 40 <= qrs_ms <= 200:
                qrs_per_beat.append(qrs_ms); qrs_start_idxs.append(qs); qrs_end_idxs.append(qe)
        except Exception:
            pass
    qrs_median_ms = float(np.median(qrs_per_beat)) if qrs_per_beat else 0.0
    print("\n[Step 7] QRS Duration (Curtin 2018)")
    print("  Per-beat QRS : %s" % [round(v,1) for v in qrs_per_beat[:8]])
    print("  Median QRS   : %.1f ms -> %d ms" % (qrs_median_ms, int(round(qrs_median_ms))))
    results["qrs_per_beat"]   = qrs_per_beat
    results["qrs_median_ms"]  = qrs_median_ms
    results["qrs_start_idxs"] = qrs_start_idxs
    results["qrs_end_idxs"]   = qrs_end_idxs

    qrs_start_ref = detectQRSStartAdaptive(filt, r_curr, windows)
    qrs_end_ref   = detectQRSEndAdaptive(filt, r_curr, windows)
    measured_qrs  = (qrs_end_ref - qrs_start_ref) / fs * 1000.0
    print("\n[Step 8] QRS Onset/Offset (ref beat @ sample %d)" % r_curr)
    print("  QRS onset  idx : %d  (%.1f ms)" % (qrs_start_ref, qrs_start_ref/fs*1000))
    print("  QRS offset idx : %d  (%.1f ms)" % (qrs_end_ref, qrs_end_ref/fs*1000))
    print("  Onset->Offset  : %.1f ms" % measured_qrs)
    results["qrs_start_ref"] = qrs_start_ref
    results["qrs_end_ref"]   = qrs_end_ref

    pr_ms = 0
    try:
        from ecg.ecg_calculations import detectPWavesImproved, calculatePRIntervalsImproved
        qrs_starts_all = [detectQRSStartAdaptive(filt, int(rp), windows) for rp in r_peaks]
        p_waves  = detectPWavesImproved(filt, r_peaks, windows, hr_bpm, qrs_starts_all, fs)
        pr_list  = calculatePRIntervalsImproved(signal=filt, p_waves=p_waves,
                                                 r_peaks=r_peaks, fs=fs, heart_rate=hr_bpm)
        valid_pr = [v for v in pr_list if v > 0]
        if valid_pr:
            pr_ms = int(round(float(np.median(valid_pr))))
    except Exception as e:
        print("  PR detection error: %s" % e)
    print("\n[Step 9] PR Interval : %d ms" % pr_ms)
    results["pr_ms"] = pr_ms

    qt_ms=0.0; qtc_ms=0; qtcf_ms=0
    r_next = int(r_peaks[-1]) if len(r_peaks) >= 2 else r_curr
    try:
        from ecg.ecg_calculations import detectTWaveEndAdaptive
        t_end  = detectTWaveEndAdaptive(filt, r_curr, qrs_start_ref, r_next,
                                         windows, rr_sec, hr_bpm, fs)
        qt_raw = (t_end - qrs_start_ref) / fs * 1000.0
        qt_min = 150.0 if hr_bpm > 200 else (170.0 if hr_bpm > 150 else 200.0)
        if qt_min <= qt_raw <= 700.0:
            qt_ms = qt_raw
    except Exception as e:
        print("  QT detection error: %s" % e)
    if qt_ms > 0 and rr_median_ms > 0:
        from ecg.ecg_calculations import calculate_qtc_bazett, calculate_qtcf_interval
        qtc_ms  = calculate_qtc_bazett(qt_ms, rr_median_ms)
        qtcf_ms = calculate_qtcf_interval(qt_ms, rr_median_ms)
    print("\n[Step 10] QT + QTc")
    print("  QT             : %.1f ms" % qt_ms)
    print("  QTc  (Bazett)  : %d ms  [QT / sqrt(RR_sec)]" % qtc_ms)
    print("  QTcF (Frideric): %d ms  [QT / RR^(1/3)]" % qtcf_ms)
    results["qt_ms"]=qt_ms; results["qtc_ms"]=qtc_ms; results["qtcf_ms"]=qtcf_ms

    print("\n" + "-"*60)
    print("  FINAL CALCULATED VALUES (matching ReportScreen display):")
    print("  HR   = %d bpm" % hr_bpm)
    print("  RR   = %.0f ms" % rr_median_ms)
    print("  PR   = %d ms"   % pr_ms)
    print("  QRS  = %d ms"   % int(round(qrs_median_ms)))
    print("  QT   = %.0f ms" % qt_ms)
    print("  QTc  = %d ms  (Bazett)" % qtc_ms)
    print("  QTcF = %d ms  (Fridericia)" % qtcf_ms)
    print("-"*60 + "\n")
    return results

def draw_ecg_grid(ax, x_max, y_min, y_max):
    ax.set_facecolor(ECG_PAPER_BG)
    minor_x=20; major_x=100; minor_y=0.1; major_y=0.5
    x=0
    while x <= x_max:
        ax.axvline(x, color=ECG_GRID_MINOR, linewidth=0.4, zorder=0)
        x += minor_x
    x=0
    while x <= x_max:
        ax.axvline(x, color=ECG_GRID_MAJOR, linewidth=0.8, zorder=0)
        x += major_x
    y=y_min
    while y <= y_max + 0.01:
        ax.axhline(y, color=ECG_GRID_MINOR, linewidth=0.4, zorder=0)
        y = round(y + minor_y, 5)
    y = round(np.ceil(y_min / major_y) * major_y, 5)
    while y <= y_max + 0.01:
        ax.axhline(y, color=ECG_GRID_MAJOR, linewidth=0.8, zorder=0)
        y = round(y + major_y, 5)

def plot_qrs_visualization(results, fs=ECG_FS, out_path=None, show_seconds=10.0):
    filtered   = results.get("filtered")
    r_peaks    = results.get("r_peaks", np.array([]))
    qrs_starts = results.get("qrs_start_idxs", [])
    qrs_ends   = results.get("qrs_end_idxs", [])
    if filtered is None:
        print("  Nothing to plot.")
        return
    signal_mv = filtered / ADC_PER_MV
    n_show    = min(int(show_seconds * fs), len(signal_mv))
    sig       = signal_mv[:n_show]
    t         = np.arange(n_show)
    rp_vis    = r_peaks[r_peaks < n_show]
    qs_vis    = [(s, e, i) for i, (s, e) in enumerate(zip(qrs_starts, qrs_ends))
                  if s < n_show and e < n_show]
    y_min = max(sig.min() - 0.2, -2.5)
    y_max = min(sig.max() + 0.2,  2.5)
    hr=results.get("hr_bpm",0); qrs=int(round(results.get("qrs_median_ms",0)))
    rr=results.get("rr_median_ms",0); pr=results.get("pr_ms",0)
    qt=results.get("qt_ms",0); qtc=results.get("qtc_ms",0); qtcf=results.get("qtcf_ms",0)

    fig = plt.figure(figsize=(20, 12), facecolor="#1a1a2e")
    gs  = GridSpec(3, 3, figure=fig, left=0.05, right=0.98, top=0.92, bottom=0.06,
                   hspace=0.48, wspace=0.35)
    ax_ecg=fig.add_subplot(gs[0,:]); ax_zoom=fig.add_subplot(gs[1,:2])
    ax_metrics=fig.add_subplot(gs[1,2]); ax_qrs_bar=fig.add_subplot(gs[2,0])
    ax_rr=fig.add_subplot(gs[2,1]); ax_steps=fig.add_subplot(gs[2,2])

    fig.suptitle("QRS Calculation Visualizer  --  ReportScreen (3).kt Pipeline",
                 color="white", fontsize=16, fontweight="bold", y=0.97)

    draw_ecg_grid(ax_ecg, n_show, y_min, y_max)
    ax_ecg.plot(t, sig, color="#1a1a1a", linewidth=0.9, zorder=5, label="Lead II")
    if len(rp_vis) > 0:
        ax_ecg.scatter(rp_vis, sig[rp_vis], color="#e74c3c", s=60, zorder=10,
                       label="R-peaks (%d)" % len(rp_vis), marker="^")
    for (qs, qe, idx) in qs_vis:
        ax_ecg.axvspan(qs, qe, alpha=0.22, color="#2ecc71", zorder=3)
        if idx < 5:
            mid=( qs+qe)/2; dur=(qe-qs)/fs*1000.0
            ax_ecg.text(mid, y_max*0.82, "%.0fms" % dur, ha="center", va="bottom",
                        fontsize=7, color="#27ae60", fontweight="bold", zorder=11)
    ax_ecg.set_xlim(0, n_show); ax_ecg.set_ylim(y_min, y_max)
    ax_ecg.set_facecolor(ECG_PAPER_BG)
    ax_ecg.set_xlabel("Samples (500 Hz -> 500 samples = 1 s)", color="#555", fontsize=9)
    ax_ecg.set_ylabel("Amplitude (mV)", color="#555", fontsize=9)
    ax_ecg.set_title("Lead II ECG -- %.0fs window | HR=%d bpm | QRS=%d ms | PR=%d ms | QTc=%d ms" %
                     (show_seconds, hr, qrs, pr, qtc), color="white", fontsize=11, pad=6)
    ax_ecg.tick_params(colors="#555")
    for sp in ax_ecg.spines.values(): sp.set_color("#ccc")
    ax_ecg.legend(loc="upper right", fontsize=8, facecolor="#f9f9f9", edgecolor="#ccc")

    if len(rp_vis) >= 2:
        ref_rp=int(rp_vis[len(rp_vis)//2]); zoom_w=int(rr*1.2) if rr>0 else int(0.8*fs)
        z_start=max(0,ref_rp-zoom_w//2); z_end=min(n_show, z_start+zoom_w)
        z_sig=sig[z_start:z_end]
        draw_ecg_grid(ax_zoom, z_end-z_start, z_sig.min()-0.1, z_sig.max()+0.1)
        ax_zoom.plot(np.arange(z_end-z_start), z_sig, color="#1a1a1a", linewidth=1.6, zorder=5)
        ax_zoom.scatter(ref_rp-z_start, sig[ref_rp], color="#e74c3c", s=140, zorder=10,
                        marker="^", label="R-peak")
        qs_ref=results.get("qrs_start_ref"); qe_ref=results.get("qrs_end_ref")
        if qs_ref is not None and qe_ref is not None:
            qs_r=qs_ref-z_start; qe_r=qe_ref-z_start
            ax_zoom.axvline(qs_r, color="#2ecc71", linewidth=2.0, linestyle="--", zorder=9, label="QRS onset")
            ax_zoom.axvline(qe_r, color="#e67e22", linewidth=2.0, linestyle="--", zorder=9, label="QRS offset")
            ax_zoom.axvspan(qs_r, qe_r, alpha=0.25, color="#2ecc71", zorder=3)
            mid_r=(qs_r+qe_r)/2
            ax_zoom.text(mid_r, z_sig.max()*0.6, "QRS\n%.0f ms" % ((qe_ref-qs_ref)/fs*1000),
                         ha="center", va="center", fontsize=11, color="#155724", fontweight="bold",
                         bbox=dict(boxstyle="round,pad=0.4", fc="#d4edda", ec="#28a745", lw=1.5))
        ax_zoom.set_xlim(0, z_end-z_start); ax_zoom.set_facecolor(ECG_PAPER_BG)
        ax_zoom.set_title("Zoomed Beat  (QRS onset / offset annotated)", color="white", fontsize=10)
        ax_zoom.set_xlabel("Samples (relative)", color="#555", fontsize=9)
        ax_zoom.set_ylabel("mV", color="#555", fontsize=9)
        ax_zoom.tick_params(colors="#555")
        for sp in ax_zoom.spines.values(): sp.set_color("#ccc")
        ax_zoom.legend(loc="upper right", fontsize=8, facecolor="#f9f9f9", edgecolor="#ccc")

    ax_metrics.set_facecolor("#0f0f23"); ax_metrics.axis("off")
    metrics_data = [
        ("Heart Rate",   "%d bpm" % hr,    "#e74c3c"),
        ("RR Interval",  "%.0f ms" % rr,   "#3498db"),
        ("PR Interval",  "%d ms" % pr,     "#9b59b6"),
        ("QRS Duration", "%d ms" % qrs,    "#2ecc71"),
        ("QT Interval",  "%.0f ms" % qt,   "#f39c12"),
        ("QTc (Bazett)", "%d ms" % qtc,    "#1abc9c"),
        ("QTcF (Frid.)", "%d ms" % qtcf,   "#e91e63"),
    ]
    ax_metrics.text(0.5, 0.97, "ECG Metrics", transform=ax_metrics.transAxes,
                    ha="center", va="top", fontsize=13, fontweight="bold", color="white")
    for i, (label, value, color) in enumerate(metrics_data):
        y_pos = 0.85 - i * 0.12
        fancy = mpatches.FancyBboxPatch((0.03, y_pos-0.045), 0.94, 0.10,
                                        boxstyle="round,pad=0.01",
                                        facecolor=color+"22", edgecolor=color,
                                        linewidth=1.4, transform=ax_metrics.transAxes, clip_on=False)
        ax_metrics.add_patch(fancy)
        ax_metrics.text(0.10, y_pos+0.01, label, transform=ax_metrics.transAxes,
                        ha="left", va="center", fontsize=8.5, color="#cccccc")
        ax_metrics.text(0.92, y_pos+0.01, value, transform=ax_metrics.transAxes,
                        ha="right", va="center", fontsize=11, fontweight="bold", color=color)
    ax_metrics.text(0.5, 0.015, "Curtin 2018 + Pan-Tompkins\nAdaptive Windows | Bazett QTc",
                    transform=ax_metrics.transAxes, ha="center", va="bottom",
                    fontsize=7, color="#888888", style="italic")

    qrs_vals=results.get("qrs_per_beat",[])
    ax_qrs_bar.set_facecolor("#0f0f23")
    if qrs_vals:
        x_b=np.arange(len(qrs_vals))
        colors_b=["#2ecc71" if 60<=v<=110 else "#e74c3c" for v in qrs_vals]
        ax_qrs_bar.bar(x_b, qrs_vals, color=colors_b, edgecolor="#333", linewidth=0.5, zorder=5)
        med_v=float(np.median(qrs_vals))
        ax_qrs_bar.axhline(med_v, color="#f39c12", linewidth=1.8, linestyle="--", zorder=6,
                           label="Median %.0f ms" % med_v)
        ax_qrs_bar.axhspan(60, 110, alpha=0.07, color="#2ecc71", label="Normal 60-110 ms")
        ax_qrs_bar.set_title("QRS Duration per Beat", color="white", fontsize=10)
        ax_qrs_bar.set_xlabel("Beat index", color="#aaa", fontsize=8)
        ax_qrs_bar.set_ylabel("ms", color="#aaa", fontsize=8)
        ax_qrs_bar.tick_params(colors="#aaa")
        ax_qrs_bar.legend(fontsize=7, facecolor="#1a1a2e", edgecolor="#555", labelcolor="#ccc")
        for sp in ax_qrs_bar.spines.values(): sp.set_color("#555")
    else:
        ax_qrs_bar.text(0.5, 0.5, "No QRS data", ha="center", va="center",
                        color="#888", transform=ax_qrs_bar.transAxes, fontsize=12)

    rr_vals=results.get("valid_rr_ms", np.array([]))
    ax_rr.set_facecolor("#0f0f23")
    if len(rr_vals) > 1:
        ax_rr.plot(rr_vals, color="#3498db", linewidth=1.8, zorder=5, marker="o",
                   markersize=4, markerfacecolor="#e74c3c")
        ax_rr.axhline(float(np.median(rr_vals)), color="#f39c12", linewidth=1.6,
                      linestyle="--", label="Median %.0f ms" % np.median(rr_vals))
        ax_rr.fill_between(range(len(rr_vals)), rr_vals, alpha=0.18, color="#3498db")
        ax_rr.set_title("RR Interval Tachogram", color="white", fontsize=10)
        ax_rr.set_xlabel("Beat index", color="#aaa", fontsize=8)
        ax_rr.set_ylabel("RR (ms)", color="#aaa", fontsize=8)
        ax_rr.tick_params(colors="#aaa")
        ax_rr.legend(fontsize=7, facecolor="#1a1a2e", edgecolor="#555", labelcolor="#ccc")
        for sp in ax_rr.spines.values(): sp.set_color("#555")

    ax_steps.set_facecolor("#0f0f23"); ax_steps.axis("off")
    ax_steps.set_title("Calculation Pipeline", color="white", fontsize=10, pad=4)
    w_obj=results.get("windows")
    steps_info = [
        ("1  ADC to mV",         "/ %.1f  (Kotlin ADC_PER_MV)" % ADC_PER_MV,      "#3498db"),
        ("2  DC-offset Remove",  "Median baseline subtract",                         "#9b59b6"),
        ("3  Bandpass 0.5-40Hz", "Butterworth 2nd order, filtfilt",                  "#1abc9c"),
        ("4  R-peak Detection",  "Pan-Tompkins algorithm",                            "#e74c3c"),
        ("5  HR + RR",           "HR=%d bpm  RR=%.0f ms" % (hr, rr),               "#f39c12"),
        ("6  Adaptive Windows",  "qrsOnset=%s smp" % str(getattr(w_obj,"qrsOnsetSearch","-")) if w_obj else "", "#2ecc71"),
        ("7  QRS Duration",      "Curtin 2018 -> %d ms" % qrs,                      "#e67e22"),
        ("8  PR Interval",       "P-wave detect -> %d ms" % pr,                      "#8e44ad"),
        ("9  QT + QTc",          "QT=%.0fms  QTc=%dms  QTcF=%dms" % (qt,qtc,qtcf),"#16a085"),
    ]
    for i, (name, detail, color) in enumerate(steps_info):
        y_pos = 0.96 - i * 0.105
        fancy = mpatches.FancyBboxPatch((0.01, y_pos-0.038), 0.98, 0.078,
                                        boxstyle="round,pad=0.01",
                                        facecolor=color+"18", edgecolor=color+"99",
                                        linewidth=0.9, transform=ax_steps.transAxes, clip_on=False)
        ax_steps.add_patch(fancy)
        ax_steps.text(0.05, y_pos+0.014, name, transform=ax_steps.transAxes,
                      ha="left", va="center", fontsize=7.5, fontweight="bold", color=color)
        ax_steps.text(0.05, y_pos-0.014, detail, transform=ax_steps.transAxes,
                      ha="left", va="center", fontsize=6.5, color="#aaaaaa")

    if out_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(_REPO_ROOT, "qrs_visualization_%s.png" % ts)
    plt.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="#1a1a2e")
    print("\n  Graph saved -> %s" % out_path)
    plt.close(fig)
    return out_path

def main():
    parser = argparse.ArgumentParser(description="QRS Calculation Visualizer")
    parser.add_argument("--json", help="Path to ECG JSON file")
    parser.add_argument("--csv",  help="Path to CSV file")
    parser.add_argument("--lead",    default="II")
    parser.add_argument("--fs",      type=float, default=ECG_FS)
    parser.add_argument("--out",     help="Output PNG path")
    parser.add_argument("--seconds", type=float, default=10.0)
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  QRS CALCULATION VISUALIZER")
    print("  Mirrors: ReportScreen (3).kt + ecg_calculations.py")
    print("="*60)

    raw_signal = None
    if args.json:
        print("\n  Loading from JSON: %s" % args.json)
        raw_signal = load_from_json(args.json, args.lead)
    elif args.csv:
        print("\n  Loading from CSV: %s" % args.csv)
        raw_signal = load_from_csv(args.csv)
    else:
        history_path = os.path.join(_REPO_ROOT, "ecg_history.json")
        if os.path.exists(history_path):
            print("\n  Auto-loading from: %s" % history_path)
            try:
                raw_signal = load_from_history(history_path, args.lead)
            except Exception as e:
                print("  Could not load history: %s" % e)
    if raw_signal is None:
        print("\n  No ECG data found -- generating synthetic ECG.")
        raw_signal = generate_synthetic_ecg(n=int(args.seconds * args.fs + 500), fs=args.fs)

    results  = run_qrs_pipeline(raw_signal, fs=args.fs, label="Lead %s" % args.lead)
    out_path = plot_qrs_visualization(results, fs=args.fs, out_path=args.out,
                                      show_seconds=args.seconds)
    print("\n  Done! Graph -> %s\n" % out_path)
    return out_path

if __name__ == "__main__":
    main()
