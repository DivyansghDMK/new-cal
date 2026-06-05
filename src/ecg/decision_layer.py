"""
ECG Diagnostics Decision Layer
==============================
Implements the 7-step decision pipeline for robust, clinical-grade ECG interpretation:
1. Signal Quality Gate (Multi-factor SQI model)
2. Measurement Validation
3. Rhythm Classification
4. Confidence Evidence Model
5. Persistence Filtering (Hysteresis)
6. Conflict Resolution (Physiological Consistency)
7. Final Interpretation Selection (Priority-based selection)
"""

import numpy as np
from typing import List, Dict, Any, Tuple
from .diagnosis_hysteresis import apply_diagnosis_hysteresis
from .physiological_consistency import validate_diagnoses, get_last_audit_log
from .lead_capability_matrix import get_lead_capabilities
import logging as _logging
_dl_logger = _logging.getLogger("DecisionLayer")

# Priority lists
CRITICAL = {"Asystole", "Ventricular Fibrillation", "VFib", "VF", "Ventricular Tachycardia", "VT", "VTach"}
MAJOR = {"Atrial Fibrillation", "AFib", "AF", "Atrial Flutter", "Flutter", "Third-degree AV Block", 
         "Complete AV Block", "Second-degree AV Block", "Mobitz I", "Mobitz II", "First-degree AV Block"}
MINOR = {"PVC", "Frequent PVCs", "Multifocal PVCs", "Borderline QTc", "Borderline Wide QRS",
         "Left Bundle Branch Block", "LBBB", "Right Bundle Branch Block", "RBBB"}

def calculate_sqi(
    signal: np.ndarray,
    fs: float,
    rr_intervals_ms: np.ndarray
) -> Tuple[float, Dict[str, float]]:
    """
    Computes a multi-factor Signal Quality Index (SQI) based on:
    SQI = 0.35 * snr_score + 0.25 * saturation_score + 0.20 * rr_consistency + 0.20 * baseline_wander_score
    """
    if signal.size == 0:
        return 0.0, {"snr": 0.0, "saturation": 0.0, "rr_consistency": 0.0, "baseline_wander": 0.0}
        
    # 1. SNR Score
    amplitude = float(np.ptp(signal))
    noise = float(np.std(np.diff(signal)))
    snr = amplitude / max(noise, 1e-6)
    snr_score = float(max(0.0, min(1.0, (snr - 1.0) / 8.0)))
    
    # 2. Saturation Score
    # Fraction of samples within non-saturated range (assumed clipping at ±3.8 mV)
    saturated_samples = np.sum(np.abs(signal) > 3.8)
    saturation_score = float(1.0 - (saturated_samples / signal.size))
    
    # 3. RR Consistency Score
    if rr_intervals_ms.size >= 2:
        rr_mean = float(np.mean(rr_intervals_ms))
        rr_std = float(np.std(rr_intervals_ms))
        cv = rr_std / max(rr_mean, 1e-9)
        rr_consistency = float(max(0.0, min(1.0, 1.0 - cv)))
    else:
        rr_consistency = 1.0
        
    # 4. Baseline Wander Score
    # Low pass filtered baseline standard deviation
    window_size = int(fs * 0.8) # 800ms window
    if window_size > 0 and signal.size > window_size:
        kernel = np.ones(window_size) / window_size
        baseline = np.convolve(signal - np.mean(signal), kernel, mode='same')
        wander_std = float(np.std(baseline))
        baseline_wander_score = float(max(0.0, min(1.0, 1.0 - wander_std * 2.5)))
    else:
        baseline_wander_score = 1.0
        
    sqi = 0.35 * snr_score + 0.25 * saturation_score + 0.20 * rr_consistency + 0.20 * baseline_wander_score
    scores = {
        "snr": snr_score,
        "saturation": saturation_score,
        "rr_consistency": rr_consistency,
        "baseline_wander": baseline_wander_score
    }
    return float(sqi), scores

def validate_measurements(metrics: Dict[str, Any]) -> Tuple[float, List[str]]:
    """
    Step 2: Measurement Validation.
    Validates ECG interval measurements and returns a confidence deduction score and flags.
    """
    warnings = []
    confidence_multiplier = 1.0
    
    pr = float(metrics.get("pr_ms") or metrics.get("PR") or 0.0)
    qrs = float(metrics.get("qrs_ms") or metrics.get("QRS") or 0.0)
    qt = float(metrics.get("qt_ms") or 0.0)
    hr = float(metrics.get("heart_rate_bpm") or 0.0)
    
    # PR Validation
    if pr > 0:
        if pr < 80.0 or pr > 320.0:
            warnings.append("Physiologically abnormal PR interval")
            confidence_multiplier *= 0.85
            
    # QRS Validation
    if qrs > 0:
        if qrs < 40.0 or qrs > 250.0:
            warnings.append("Physiologically abnormal QRS duration")
            confidence_multiplier *= 0.80
            
    # QT Validation
    if qt > 0:
        if qt < 200.0 or qt > 750.0:
            warnings.append("Physiologically abnormal QT interval")
            confidence_multiplier *= 0.90
            
    # HR Validation
    if hr > 0:
        if hr < 30.0 or hr > 250.0:
            warnings.append("Extreme heart rate recorded")
            confidence_multiplier *= 0.95
            
    return confidence_multiplier, warnings

def build_confidence_evidence_model(
    engine_diagnoses: List[str],
    metrics: Dict[str, Any],
    features: Dict[str, Any],
    base_confidence: float
) -> List[Dict[str, Any]]:
    """
    Step 4: Confidence Evidence Model.
    Builds diagnostic objects with confidence scores and evidence lists.
    """
    candidates = []
    
    hr = float(metrics.get("heart_rate_bpm") or 0.0)
    pr = float(metrics.get("pr_ms") or metrics.get("PR") or 0.0)
    qrs = float(metrics.get("qrs_ms") or metrics.get("QRS") or 0.0)
    qtc = float(metrics.get("qtc_bazett") or 0.0)
    
    p_detected = bool(features.get("p_detected") or features.get("p_present"))
    rr_std = float(features.get("rr_std") or 0.0)
    rr_regular = rr_std < 80.0
    
    for diag in engine_diagnoses:
        evidence = []
        conf = base_confidence
        
        if diag == "Normal Sinus Rhythm":
            if p_detected:
                evidence.append("Stable P waves detected")
            if rr_regular:
                evidence.append("Stable regular RR intervals")
            if 60.0 <= hr <= 100.0:
                evidence.append(f"Normal resting heart rate ({hr:.0f} bpm)")
            if 120.0 <= pr <= 200.0:
                evidence.append(f"Normal PR interval ({pr:.0f} ms)")
                
        elif diag == "Sinus Bradycardia":
            if p_detected:
                evidence.append("Stable P waves detected")
            if hr < 60.0:
                evidence.append(f"Heart rate is slow ({hr:.0f} bpm)")
                
        elif diag == "Sinus Tachycardia":
            if p_detected:
                evidence.append("Stable P waves detected")
            if hr > 100.0:
                evidence.append(f"Heart rate is elevated ({hr:.0f} bpm)")
                
        elif diag in ("Atrial Fibrillation", "AFib", "AF"):
            if not p_detected:
                evidence.append("Absence of P waves")
            if not rr_regular:
                evidence.append(f"Irregular RR intervals (RR std = {rr_std:.1f} ms)")
            else:
                conf *= 0.5 # Substantially reduce AFib confidence if RR is highly regular
                
        elif diag in ("Atrial Flutter", "Flutter"):
            flutter_score = float(features.get("flutter_score") or 0.0)
            evidence.append(f"Flutter wave spectral evidence detected (score = {flutter_score:.2f})")
            if features.get("atrial_rate_bpm"):
                evidence.append(f"Atrial rate is {features['atrial_rate_bpm']:.0f} bpm")
                
        elif diag in ("Third-degree AV Block", "Complete AV Block"):
            if features.get("av_dissociation"):
                evidence.append("Evidence of AV dissociation")
            if hr < 50.0:
                evidence.append(f"Bradycardia present ({hr:.0f} bpm)")
            if not p_detected:
                conf *= 0.7
                
        elif diag in ("Ventricular Fibrillation", "VFib", "VF"):
            vf_score = float(features.get("vf_score") or 0.0)
            evidence.append(f"Chaotic spectral waveform detected (VF score = {vf_score:.2f})")
            if not features.get("organized_qrs", True):
                evidence.append("No organized QRS complexes detected")
                
        elif diag == "Asystole":
            sig_amp = float(features.get("signal_amplitude") or 0.0)
            evidence.append(f"Ventricular flatline / very low amplitude ({sig_amp:.3f} mV)")
            
        elif "bundle branch block" in diag.lower() or "lbbb" in diag.lower() or "rbbb" in diag.lower():
            evidence.append(f"Wide QRS complex ({qrs:.1f} ms >= 120 ms)")
            if "left" in diag.lower() or "lbbb" in diag.lower():
                evidence.append("LBBB morphology present in V1/V6")
            else:
                evidence.append("RBBB morphology present in V1/V6")
                
        else:
            evidence.append("Rhythm matches algorithmic detection criteria")
            
        candidates.append({
            "diagnosis": diag,
            "confidence": float(max(0.0, min(1.0, conf))),
            "evidence": evidence
        })
        
    return candidates

def process_decision_layer(
    instance_id: str,
    raw_signal: np.ndarray,
    fs: float,
    r_peaks: np.ndarray,
    rr_intervals_ms: np.ndarray,
    metrics: Dict[str, Any],
    features: Dict[str, Any],
    engine_diagnoses: List[str],
    available_leads: List[str],
    human_safety_mode: bool = False
) -> Dict[str, Any]:
    """
    Executes the 7-step decision pipeline.
    """
    # Step 1: Signal Quality Gate
    # Arrhythmia detector might have pre-computed SNR and saturation
    snr_score = float(features.get("snr") or features.get("signal_snr") or 0.8)
    saturation_score = float(features.get("saturation") or 1.0)
    
    sqi, sqi_details = calculate_sqi(raw_signal, fs, rr_intervals_ms)
    
    # Overwrite if we have more specific calculations
    sqi_details["snr"] = max(sqi_details["snr"], snr_score)
    sqi_details["saturation"] = min(sqi_details["saturation"], saturation_score)
    sqi = 0.35 * sqi_details["snr"] + 0.25 * sqi_details["saturation"] + 0.20 * sqi_details["rr_consistency"] + 0.20 * sqi_details["baseline_wander"]
    
    # Gate interpretation if SQI is poor
    if sqi < 0.5:
        _dl_logger.debug(
            f"[SQI_GATE] instance={instance_id} sqi={sqi:.3f} — interpretation disabled"
        )
        return {
            "sqi": sqi,
            "sqi_details": sqi_details,
            "interpretation_disabled": True,
            "diagnoses": [{
                "diagnosis": "Poor Signal Quality",
                "confidence": 0.3,
                "evidence": ["SQI is below interpretation gate threshold of 0.5"]
            }],
            "audit_log": [
                {
                    "diagnosis": "ALL",
                    "rejected": True,
                    "rejection_reason": f"SQI gate blocked interpretation (SQI={sqi:.3f} < 0.50)"
                }
            ],
            "lead_capabilities": get_lead_capabilities(available_leads)
        }
        
    # Step 2: Measurement Validation
    measurement_mult, warnings = validate_measurements(metrics)
    base_conf = float(metrics.get("Confidence") or 0.8) * measurement_mult
    
    # Step 3: Rhythm Classification (done via engine_diagnoses input)
    
    # Step 4: Confidence Evidence Model
    candidates = build_confidence_evidence_model(engine_diagnoses, metrics, features, base_conf)
    
    # Step 5: Persistence Filtering (Hysteresis)
    # Using 5 windows for activation, 3 for deactivation
    candidates = apply_diagnosis_hysteresis(instance_id, candidates, activate_threshold=5, deactivate_threshold=3)

    # Emit hysteresis audit entries for any suppressed diagnoses
    for cand in candidates:
        if not cand.get("activated", True):
            _dl_logger.debug(
                f"[HYSTERESIS] {cand['diagnosis']} suppressed — "
                f"activation_count={cand.get('activation_count', '?')}/5"
            )

    # Step 6: Conflict Resolution (Physiological Consistency)
    candidates = validate_diagnoses(candidates, metrics, features)

    # Retrieve full audit log from the consistency engine
    consistency_audit = get_last_audit_log()
    for entry in consistency_audit:
        if entry.get("rejected"):
            _dl_logger.debug(
                f"[CONSISTENCY_REJECT] {entry['diagnosis']} — {entry['rejection_reason']}"
            )
    
    # Step 7: Final Interpretation Selection (Priority classification)
    # Apply human safety mode thresholds if enabled
    # Safety mode thresholds: AFib >= 0.90, Flutter >= 0.92, VFib >= 0.98, Third-degree AV Block >= 0.95
    if human_safety_mode:
        safe_candidates = []
        for cand in candidates:
            name = cand["diagnosis"]
            conf = cand["confidence"]
            
            if name in ("Atrial Fibrillation", "AFib", "AF") and conf < 0.90:
                continue
            if name in ("Atrial Flutter", "Flutter") and conf < 0.92:
                continue
            if name in ("Ventricular Fibrillation", "VFib", "VF") and conf < 0.98:
                continue
            if name in ("Third-degree AV Block", "Complete AV Block") and conf < 0.95:
                continue
            safe_candidates.append(cand)
        candidates = safe_candidates
        
    # Sort by priority
    def get_priority(name: str) -> int:
        if name in CRITICAL:
            return 3
        if name in MAJOR:
            return 2
        if name in MINOR:
            return 1
        return 0
        
    candidates.sort(key=lambda c: (get_priority(c["diagnosis"]), c["confidence"]), reverse=True)
    
    # Lead-aware filtering: Apply Lead Capability Matrix
    capabilities = get_lead_capabilities(available_leads)
    filtered_candidates = []
    for cand in candidates:
        name = cand["diagnosis"]
        # If ST/MI/LVH diagnostics are disabled by lead count, filter them out
        if not capabilities["st_analysis"] and any(term in name.lower() for term in ("st elevation", "st depression", "st-t changes")):
            continue
        if not capabilities["mi_localization"] and any(term in name.lower() for term in ("myocardial infarction", "infarct", "anterior mi", "inferior mi")):
            continue
        if not capabilities["lvh"] and "lvh" in name.lower():
            continue
        filtered_candidates.append(cand)
        
    # If no candidate survived, fallback to Sinus Rhythm or Unknown
    if not filtered_candidates:
        filtered_candidates.append({
            "diagnosis": "Normal Sinus Rhythm" if features.get("p_detected") else "Sinus Rhythm",
            "confidence": 0.8,
            "evidence": ["Default fallback after decision layer filtering"]
        })
        
    # Emit final interpretation log
    for cand in filtered_candidates:
        _dl_logger.debug(
            f"[FINAL] {cand['diagnosis']} conf={cand.get('confidence', cand.get('final_confidence', 0)):.2f} "
            f"evidence={cand.get('evidence', [])}"
        )

    return {
        "sqi": sqi,
        "sqi_details": sqi_details,
        "interpretation_disabled": False,
        "diagnoses": filtered_candidates,
        "warnings": warnings,
        "lead_capabilities": capabilities,
        "audit_log": consistency_audit,
    }
