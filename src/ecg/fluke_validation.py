"""
Fluke Calibration Validation Framework
======================================
Validates measured interval and rhythm diagnostic accuracy against Fluke simulator
reference settings. Compares HR, PR, QRS, QT, and QTc intervals and outputs error stats.
"""

import numpy as np
from typing import Dict, Any, List, Tuple
from .arrhythmia_detector import ArrhythmiaDetector, analyze_ecg

# Fluke reference values for standard simulation settings
FLUKE_REFERENCE_TABLE = {
    "NSR_60": {
        "description": "Normal Sinus Rhythm at 60 BPM",
        "reference": {"hr": 60.0, "pr": 160.0, "qrs": 80.0, "qt": 400.0, "qtc": 400.0},
        "rhythm": "Normal Sinus Rhythm"
    },
    "NSR_120": {
        "description": "Normal Sinus Rhythm at 120 BPM",
        "reference": {"hr": 120.0, "pr": 140.0, "qrs": 80.0, "qt": 320.0, "qtc": 452.5},
        "rhythm": "Sinus Tachycardia"
    },
    "LBBB_75": {
        "description": "Left Bundle Branch Block at 75 BPM",
        "reference": {"hr": 75.0, "pr": 170.0, "qrs": 140.0, "qt": 420.0, "qtc": 469.5},
        "rhythm": "Left Bundle Branch Block"
    },
    "AFIB_90": {
        "description": "Atrial Fibrillation at 90 BPM",
        "reference": {"hr": 90.0, "pr": 0.0, "qrs": 80.0, "qt": 360.0, "qtc": 441.0},
        "rhythm": "Atrial Fibrillation"
    },
    "AVB_III_40": {
        "description": "Third-degree AV Block at 40 BPM",
        "reference": {"hr": 40.0, "pr": 0.0, "qrs": 90.0, "qt": 480.0, "qtc": 392.0},
        "rhythm": "Third-degree AV Block"
    }
}

class FlukeValidationTracker:
    def __init__(self):
        self.results = []
        
    def record_run(
        self,
        name: str,
        measured: Dict[str, float],
        reference: Dict[str, float],
        measured_rhythm: str,
        expected_rhythm: str
    ):
        self.results.append({
            "name": name,
            "measured": measured,
            "reference": reference,
            "measured_rhythm": measured_rhythm,
            "expected_rhythm": expected_rhythm
        })
        
    def generate_report(self) -> Dict[str, Any]:
        hr_errors = []
        pr_errors = []
        qrs_errors = []
        qt_errors = []
        qtc_errors = []
        
        correct_rhythms = 0
        total_runs = len(self.results)
        
        print("\n" + "=" * 80)
        print(" FLUKE SIMULATOR CALIBRATION VALIDATION REPORT")
        print("=" * 80)
        print(f"{'Test Profile':<15} | {'Metric':<6} | {'Measured':<10} | {'Expected':<10} | {'Error':<8} | {'Status':<6}")
        print("-" * 80)
        
        pass_all = True
        
        for run in self.results:
            name = run["name"]
            meas = run["measured"]
            ref = run["reference"]
            
            # Check rhythm
            rhythm_match = run["measured_rhythm"].lower() == run["expected_rhythm"].lower() or \
                           (run["expected_rhythm"] in run["measured_rhythm"])
            if rhythm_match:
                correct_rhythms += 1
                rhythm_status = "PASS"
            else:
                rhythm_status = "FAIL"
                pass_all = False
                
            print(f"{name:<15} | Rhythm | {run['measured_rhythm']:<10} | {run['expected_rhythm']:<10} | {'-':<8} | {rhythm_status:<6}")
            
            # Compare intervals
            for key, err_list, limit in [
                ("hr", hr_errors, 1.0),
                ("pr", pr_errors, 5.0),
                ("qrs", qrs_errors, 5.0),
                ("qt", qt_errors, 10.0),
                ("qtc", qtc_errors, 10.0)
            ]:
                m_val = meas.get(key, 0.0)
                r_val = ref.get(key, 0.0)
                
                # Suppress PR comparison if expected is 0 (e.g. AFib/AVB)
                if key == "pr" and r_val == 0.0:
                    continue
                    
                err = abs(m_val - r_val)
                err_list.append(err)
                
                status = "PASS" if err <= limit else "FAIL"
                if err > limit:
                    pass_all = False
                    
                print(f"{'':<15} | {key.upper():<6} | {m_val:<10.1f} | {r_val:<10.1f} | {err:<8.1f} | {status:<6}")
            print("-" * 80)
            
        # Summary statistics
        def get_stats(errors):
            if not errors:
                return 0.0, 0.0, 0.0
            return float(np.mean(errors)), float(np.median(errors)), float(np.max(errors))
            
        hr_mean, hr_med, hr_max = get_stats(hr_errors)
        pr_mean, pr_med, pr_max = get_stats(pr_errors)
        qrs_mean, qrs_med, qrs_max = get_stats(qrs_errors)
        qt_mean, qt_med, qt_max = get_stats(qt_errors)
        qtc_mean, qtc_med, qtc_max = get_stats(qtc_errors)
        
        rhythm_acc = correct_rhythms / total_runs if total_runs > 0 else 0.0
        
        print("\nSUMMARY ERROR STATISTICS:")
        print(f"HR  Error -> Mean: {hr_mean:.2f} bpm, Median: {hr_med:.2f} bpm, Max: {hr_max:.2f} bpm (Limit <= 1.0)")
        print(f"PR  Error -> Mean: {pr_mean:.2f} ms,  Median: {pr_med:.2f} ms,  Max: {pr_max:.2f} ms  (Limit <= 5.0)")
        print(f"QRS Error -> Mean: {qrs_mean:.2f} ms,  Median: {qrs_med:.2f} ms,  Max: {qrs_max:.2f} ms  (Limit <= 5.0)")
        print(f"QT  Error -> Mean: {qt_mean:.2f} ms,  Median: {qt_med:.2f} ms,  Max: {qt_max:.2f} ms  (Limit <= 10.0)")
        print(f"QTc Error -> Mean: {qtc_mean:.2f} ms,  Median: {qtc_med:.2f} ms,  Max: {qtc_max:.2f} ms  (Limit <= 10.0)")
        print(f"Rhythm Classification Accuracy: {rhythm_acc * 100:.1f}%")
        
        overall_status = "PASS" if pass_all else "FAIL"
        print(f"\nOVERALL VALIDATION STATUS: {overall_status}")
        print("=" * 80)
        
        return {
            "overall_status": overall_status,
            "rhythm_accuracy": rhythm_acc,
            "hr_stats": (hr_mean, hr_med, hr_max),
            "pr_stats": (pr_mean, pr_med, pr_max),
            "qrs_stats": (qrs_mean, qrs_med, qrs_max),
            "qt_stats": (qt_mean, qt_med, qt_max),
            "qtc_stats": (qtc_mean, qtc_med, qtc_max)
        }

def generate_synthetic_ecg(
    hr: float,
    pr: float,
    qrs: float,
    qt: float,
    fs: float = 500.0,
    duration_sec: float = 10.0,
    rhythm_type: str = "NSR"
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Generates a clean synthetic single-channel ECG signal matching the specified intervals.
    """
    n_samples = int(duration_sec * fs)
    time = np.arange(n_samples) / fs
    signal = np.zeros(n_samples)
    
    rr_sec = 60.0 / hr
    
    # Generate R-peak indices
    r_peaks = []
    curr_time = 0.5 # start first beat at 0.5s
    while curr_time < duration_sec - 0.5:
        r_peaks.append(int(curr_time * fs))
        if rhythm_type == "AFIB":
            # AFib has irregularly irregular RR intervals
            curr_time += rr_sec * np.random.uniform(0.75, 1.25)
        else:
            curr_time += rr_sec
            
    r_peaks = np.array(r_peaks, dtype=int)
    
    def gaussian(t_arr, mu, sigma, amp):
        return amp * np.exp(-0.5 * ((t_arr - mu) / sigma) ** 2)
        
    for r_idx in r_peaks:
        r_t = r_idx / fs
        
        # QRS complex parameters
        qrs_sec = qrs / 1000.0
        qrs_sigma = qrs_sec / 4.0
        
        # P wave parameters
        p_sec = 0.080
        p_sigma = p_sec / 4.0
        p_t = r_t - (pr / 1000.0) if pr > 0 else 0.0
        
        # T wave parameters
        t_sec = 0.140
        t_sigma = t_sec / 4.0
        # QT interval defines the distance from QRS start to T wave end
        # We place T peak so that T wave ends at r_t + qt - qrs/2
        t_t = r_t + (qt / 1000.0) - (qrs_sec / 2.0) - 0.080
        
        # Add P wave (unless AFIB or AVB III)
        if pr > 0 and rhythm_type not in ("AFIB", "AVB_III"):
            signal += gaussian(time, p_t, p_sigma, 0.15)
            
        # Add QRS
        signal += gaussian(time, r_t, qrs_sigma, 1.2) # R peak
        signal += gaussian(time, r_t - qrs_sec*0.2, qrs_sigma*0.5, -0.25) # Q wave
        signal += gaussian(time, r_t + qrs_sec*0.2, qrs_sigma*0.5, -0.3) # S wave
        
        # Add T wave
        signal += gaussian(time, t_t, t_sigma, 0.25)
        
    # Scale to typical ADC counts if needed, but ArrhythmiaDetector wants mV by default
    # standard baseline drift
    signal += 0.05 * np.sin(2 * np.pi * 0.1 * time)
    
    return signal, r_peaks

def run_validation():
    tracker = FlukeValidationTracker()
    fs = 500.0
    
    for name, config in FLUKE_REFERENCE_TABLE.items():
        ref = config["reference"]
        expected_rhythm = config["rhythm"]
        
        # Map profile name to rhythm type
        rhythm_type = "NSR"
        if "AFIB" in name:
            rhythm_type = "AFIB"
        elif "AVB" in name:
            rhythm_type = "AVB_III"
            
        # Generate synthetic wave
        sig, r_peaks = generate_synthetic_ecg(
            hr=ref["hr"],
            pr=ref["pr"],
            qrs=ref["qrs"],
            qt=ref["qt"],
            fs=fs,
            rhythm_type=rhythm_type
        )
        
        # Analyze using module-level analyze_ecg (ArrhythmiaDetector.detect_arrhythmias uses it internally)
        leads = {"II": sig}
        results = analyze_ecg(leads, fs=fs, patient_gender="M")
        
        measured = {
            "hr": float(results.get("heart_rate_bpm") or 0.0),
            "pr": float(results.get("pr_ms") or 0.0),
            "qrs": float(results.get("qrs_ms") or 0.0),
            "qt": float(results.get("qt_ms") or 0.0),
            "qtc": float(results.get("qtc_bazett") or 0.0)
        }
        
        measured_rhythm = results.get("Primary Diagnosis", "Unknown")
        tracker.record_run(name, measured, ref, measured_rhythm, expected_rhythm)
        
    report = tracker.generate_report()
    return report

if __name__ == "__main__":
    run_validation()
